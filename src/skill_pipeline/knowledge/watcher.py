"""Unified watcher — monitors input dir for new skills and documents."""
from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from skill_pipeline.knowledge.doc_parser import SUPPORTED_EXTENSIONS

logger = logging.getLogger(__name__)

MAX_PARALLEL = 3


def _write_doc_to_output(src: Path, output_dir: Path) -> Path:
    """Copy processed document to output/knowledge-docs/ preserving frontmatter."""
    dest_dir = output_dir / "knowledge-docs"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    # Handle collisions
    if dest.exists():
        stem, suffix = src.stem, src.suffix
        counter = 1
        while dest.exists():
            dest = dest_dir / f"{stem}-{counter}{suffix}"
            counter += 1
    shutil.copy2(src, dest)
    return dest


class UnifiedHandler(FileSystemEventHandler):
    """Watches input dir for both skill dirs and document files."""

    def __init__(
        self,
        input_dir: Path,
        output_dir: Path,
        semaphore: asyncio.Semaphore,
        loop: asyncio.AbstractEventLoop,
    ):
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.semaphore = semaphore
        self.loop = loop
        self._pending_skill_dirs: set[str] = set()

    def on_created(self, event):
        path = Path(event.src_path)

        # Case 1: A SKILL.md file was created inside a subdir
        if path.name == "SKILL.md" and path.parent != self.input_dir:
            skill_dir = path.parent
            if str(skill_dir) not in self._pending_skill_dirs:
                self._pending_skill_dirs.add(str(skill_dir))
                asyncio.run_coroutine_threadsafe(
                    self._process_skill_dir(skill_dir), self.loop
                )
            return

        # Case 2: A document file
        if not event.is_directory and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            # Skip files inside skill dirs (sub-files of skills)
            if (path.parent / "SKILL.md").exists():
                return
            asyncio.run_coroutine_threadsafe(self._process_document(path), self.loop)

    async def _process_skill_dir(self, skill_dir: Path):
        """Run the full skill pipeline for a single new skill dir."""
        async with self.semaphore:
            try:
                from skill_pipeline.skills.pipeline import run_pipeline
                from skill_pipeline.dashboard.app import broadcast
                await broadcast({"event": "processing", "type": "skill", "name": skill_dir.name})
                await run_pipeline(self.input_dir, self.output_dir)
                await broadcast({"event": "done", "type": "skill", "name": skill_dir.name})
            except Exception:
                logger.error("Skill pipeline failed for %s", skill_dir.name, exc_info=True)
            finally:
                self._pending_skill_dirs.discard(str(skill_dir))

    async def _process_document(self, path: Path):
        """Process a document file through the knowledge pipeline."""
        async with self.semaphore:
            try:
                from skill_pipeline.knowledge.chromadb_store import KnowledgeStore
                from skill_pipeline.knowledge.indexer import index_file
                from skill_pipeline.core.embedder import get_strategy
                from skill_pipeline.dashboard.app import broadcast

                await broadcast({"event": "processing", "type": "document", "name": path.name})

                strategy = get_strategy()
                store = KnowledgeStore()

                result = await index_file(
                    path, store, strategy,
                    vault_root=self.input_dir,
                    output_dir=self.output_dir,
                    delete_first=False,
                    evaluate_proposals=True,
                )

                if result is None:
                    logger.warning("No chunks from %s, skipping", path.name)
                    return

                if result.proposal_name:
                    logger.info("Generated skill proposal: %s", result.proposal_name)

                # Copy tagged file to output dir
                new_path = _write_doc_to_output(path, self.output_dir)

                logger.info("Processed %s → %s [%s] (tags: %s)",
                           path.name, new_path, result.method, ", ".join(result.tags))

                await broadcast({"event": "done", "type": "document", "name": path.name})

            except Exception:
                logger.error("Failed to process %s", path.name, exc_info=True)


async def start_watcher(
    input_dir: Path,
    output_dir: Path,
) -> None:
    """Start unified watcher on input dir. Blocks until interrupted."""
    input_dir.mkdir(parents=True, exist_ok=True)

    semaphore = asyncio.Semaphore(MAX_PARALLEL)
    loop = asyncio.get_running_loop()

    handler = UnifiedHandler(input_dir, output_dir, semaphore, loop)
    observer = Observer()
    observer.schedule(handler, str(input_dir), recursive=True)
    observer.start()

    logger.info("Watching %s for skills and documents...", input_dir)
    try:
        while True:
            await asyncio.sleep(1)
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        observer.stop()
        observer.join()
