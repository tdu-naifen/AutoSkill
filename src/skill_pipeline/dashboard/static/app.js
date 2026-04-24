/* Skill Pipeline Dashboard */

// --- WebSocket ---
let ws;
function connectWS() {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  ws = new WebSocket(`${proto}//${location.host}/ws`);
  ws.onopen = () => {
    document.getElementById("ws-status").textContent = "Connected";
    document.getElementById("ws-status").className = "status connected";
  };
  ws.onclose = () => {
    document.getElementById("ws-status").textContent = "Disconnected";
    document.getElementById("ws-status").className = "status disconnected";
    setTimeout(connectWS, 3000);
  };
  ws.onmessage = (evt) => {
    const data = JSON.parse(evt.data);
    if (data.type === "refresh") { loadGraph(); loadEmbeddings(); }
  };
}
connectWS();

// --- Pipeline Status Polling ---
async function pollStatus() {
  try {
    const data = await fetch("/api/status").then((r) => r.json());
    const el = document.getElementById("pipeline-status");
    const stage = document.getElementById("pipeline-stage");
    const msg = document.getElementById("pipeline-message");
    const elapsed = document.getElementById("pipeline-elapsed");
    const bar = document.getElementById("pipeline-bar");
    const detail = document.getElementById("pipeline-detail");

    if (data.stage === "idle") {
      el.classList.add("hidden");
    } else {
      el.classList.remove("hidden");
      stage.textContent = data.stage;
      stage.className = "stage-badge " + data.stage;
      bar.style.width = data.pct + "%";

      if (data.stage === "done") {
        msg.textContent = data.message;
        bar.style.width = "100%";
        bar.style.background = "repeating-linear-gradient(90deg, #008000 0px, #008000 8px, transparent 8px, transparent 10px)";
        if (!window._graphLoaded) {
          window._graphLoaded = true;
          loadGraph();
          loadEmbeddings();
        }
      } else if (data.stage === "extracting") {
        msg.textContent = data.message;
        detail.textContent = data.current_file || "";
      } else {
        msg.textContent = data.message || `${data.files_done}/${data.files_total}`;
        detail.textContent = data.current_file ? `Processing: ${data.current_file}` : "";
      }

      const mins = Math.floor(data.elapsed / 60);
      const secs = Math.floor(data.elapsed % 60);
      elapsed.textContent = mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;
    }
  } catch (e) {}
}
setInterval(pollStatus, 2000);
pollStatus();

// --- Fullscreen Toggle ---
function toggleFullscreen(panelId) {
  const panel = document.getElementById(panelId);
  panel.classList.toggle("fullscreen");
  if (panelId === "graph-panel") loadGraph();
  if (panelId === "umap-panel") {
    const uc = document.getElementById("umap-container");
    if (uc && uc.data) Plotly.Plots.resize(uc);
  }
}

// --- Shared state for cross-panel highlighting ---
let _umapData = [];
let _umapContainer = null;

// --- Force-Directed Graph ---
async function loadGraph() {
  const data = await fetch("/api/graph").then((r) => r.json());
  renderGraph(data);
}

function renderGraph(data) {
  const container = document.getElementById("graph-container");
  container.innerHTML = "";

  if (!data.nodes || !data.nodes.length) {
    container.innerHTML = '<p class="empty">No skills yet. Run ingest first.</p>';
    return;
  }

  // Only keep knowledge and template links (skip similarity)
  const links = data.links.filter((d) => d.type === "knowledge" || d.type === "template");
  // Only keep knowledge/template nodes that have links
  const linkedNodes = new Set();
  links.forEach((l) => {
    if (typeof l.source === "object") { linkedNodes.add(l.source.id); linkedNodes.add(l.target.id); }
    else { linkedNodes.add(l.source); linkedNodes.add(l.target); }
  });
  const nodes = data.nodes.filter((d) => d.type === "skill" || linkedNodes.has(d.id));

  const width = container.clientWidth || 600;
  const height = container.clientHeight || 550;

  const svg = d3.select(container)
    .append("svg")
    .attr("width", "100%")
    .attr("height", height);

  const g = svg.append("g");

  // Zoom
  const zoom = d3.zoom()
    .scaleExtent([0.2, 5])
    .on("zoom", (event) => g.attr("transform", event.transform));
  svg.call(zoom);

  // Count connections per knowledge node for sizing
  const knowledgeDegree = {};
  links.forEach((l) => {
    const tid = typeof l.target === "object" ? l.target.id : l.target;
    knowledgeDegree[tid] = (knowledgeDegree[tid] || 0) + 1;
  });

  const simulation = d3.forceSimulation(nodes)
    .force("link", d3.forceLink(links).id((d) => d.id).distance(80).strength(0.8))
    .force("charge", d3.forceManyBody().strength(-150))
    .force("x", d3.forceX(width / 2).strength(0.03))
    .force("y", d3.forceY((d) => {
      if (d.type === "skill") return height * 0.15;
      if (d.type === "knowledge") return height * 0.55;
      return height * 0.85; // template
    }).strength(0.4))
    .force("collision", d3.forceCollide((d) => d.type === "skill" ? 40 : 25))
    .alphaDecay(0.06)
    .alphaMin(0.01)
    .velocityDecay(0.6);

  // Links — curved
  const link = g.append("g")
    .selectAll("path")
    .data(links)
    .join("path")
    .attr("stroke", (d) => d.type === "template" ? "#808000" : "#808080")
    .attr("stroke-width", 1)
    .attr("fill", "none")
    .attr("opacity", 0.5);

  // Nodes
  const node = g.append("g")
    .selectAll("g")
    .data(nodes)
    .join("g")
    .style("cursor", "pointer")
    .call(d3.drag()
      .on("start", (event, d) => { if (!event.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
      .on("drag", (event, d) => { d.fx = event.x; d.fy = event.y; })
      .on("end", (event, d) => { if (!event.active) simulation.alphaTarget(0); d.fx = null; d.fy = null; })
    );

  // Skill nodes: rounded rect
  node.filter((d) => d.type === "skill")
    .append("rect")
    .attr("rx", 6).attr("ry", 6)
    .attr("width", (d) => d.id.length * 7.5 + 16)
    .attr("height", 26)
    .attr("x", (d) => -(d.id.length * 7.5 + 16) / 2)
    .attr("y", -13)
    .attr("fill", "#fff")
    .attr("stroke", "#000080")
    .attr("stroke-width", 1.5);

  node.filter((d) => d.type === "skill")
    .append("text")
    .attr("text-anchor", "middle")
    .attr("dy", "0.35em")
    .text((d) => d.id)
    .attr("fill", "#000080")
    .attr("font-size", "11px")
    .attr("font-weight", "700")
    .attr("font-family", "Tahoma, Geneva, sans-serif");

  // Knowledge nodes: circle with label
  node.filter((d) => d.type === "knowledge")
    .append("circle")
    .attr("r", (d) => Math.min(6 + (knowledgeDegree[d.id] || 1) * 2, 16))
    .attr("fill", "#c0c0c0")
    .attr("stroke", "#008000")
    .attr("stroke-width", 1.5);

  node.filter((d) => d.type === "knowledge")
    .append("text")
    .attr("dx", (d) => Math.min(6 + (knowledgeDegree[d.id] || 1) * 2, 16) + 4)
    .attr("dy", "0.35em")
    .text((d) => d.id.replace("k:", ""))
    .attr("fill", "#008000")
    .attr("font-size", "10px")
    .attr("font-weight", "400")
    .attr("font-family", "Tahoma, Geneva, sans-serif");

  // Template nodes: diamond
  node.filter((d) => d.type === "template")
    .append("polygon")
    .attr("points", "0,-10 10,0 0,10 -10,0")
    .attr("fill", "#fff")
    .attr("stroke", "#808000")
    .attr("stroke-width", 1.5);

  node.filter((d) => d.type === "template")
    .append("text")
    .attr("dx", 14)
    .attr("dy", "0.35em")
    .text((d) => d.id.replace("t:", ""))
    .attr("fill", "#808000")
    .attr("font-size", "10px")
    .attr("font-weight", "400")
    .attr("font-family", "Tahoma, Geneva, sans-serif");

  // Tooltip
  node.append("title")
    .text((d) => `${d.id}\n${d.description || ""}`);

  // Highlight on hover — also highlight in UMAP
  node.on("mouseover", function(event, d) {
    const connected = new Set();
    links.forEach((l) => {
      const sid = typeof l.source === "object" ? l.source.id : l.source;
      const tid = typeof l.target === "object" ? l.target.id : l.target;
      if (sid === d.id) connected.add(tid);
      if (tid === d.id) connected.add(sid);
    });
    connected.add(d.id);
    node.attr("opacity", (n) => connected.has(n.id) ? 1 : 0.15);
    link.attr("opacity", (l) => {
      const sid = typeof l.source === "object" ? l.source.id : l.source;
      const tid = typeof l.target === "object" ? l.target.id : l.target;
      return (sid === d.id || tid === d.id) ? 0.8 : 0.05;
    });
    highlightUMAP(connected);
  }).on("mouseout", function() {
    node.attr("opacity", 1);
    link.attr("opacity", 0.4);
    highlightUMAP(null);
  });

  simulation.on("tick", () => {
    link.attr("d", (d) => {
      const dx = d.target.x - d.source.x;
      const dy = d.target.y - d.source.y;
      const dr = Math.sqrt(dx * dx + dy * dy) * 1.5;
      return `M${d.source.x},${d.source.y}A${dr},${dr} 0 0,1 ${d.target.x},${d.target.y}`;
    });
    node.attr("transform", (d) => `translate(${d.x},${d.y})`);
  });
}

// --- UMAP cross-highlight ---
function highlightUMAP(connectedSet) {
  _umapContainer = document.getElementById("umap-container");
  if (!_umapData.length || !_umapContainer || !_umapContainer.data) return;

  if (!connectedSet) {
    // Reset to default
    const sizes = _umapData.map((d) => d.type === "knowledge" ? 4 : 6);
    const colors = _umapData.map((d) => d.type === "knowledge" ? "#008000" : "#000080");
    const opacities = _umapData.map(() => 0.9);
    Plotly.restyle(_umapContainer, { "marker.size": [sizes], "marker.color": [colors], "marker.opacity": [opacities] }, [0]);
    return;
  }

  const sizes = _umapData.map((d) => connectedSet.has(d.id) ? 10 : (d.type === "knowledge" ? 3 : 4));
  const colors = _umapData.map((d) => connectedSet.has(d.id) ? "#ff0000" : "#c0c0c0");
  const opacities = _umapData.map((d) => connectedSet.has(d.id) ? 1.0 : 0.2);
  Plotly.restyle(_umapContainer, { "marker.size": [sizes], "marker.color": [colors], "marker.opacity": [opacities] }, [0]);
}

// --- UMAP Scatter ---
async function loadEmbeddings() {
  const data = await fetch("/api/embeddings").then((r) => r.json());
  renderUMAP(data);
}

function renderUMAP(data) {
  const container = document.getElementById("umap-container");
  if (!data.length) {
    container.innerHTML = '<p class="empty">No embeddings yet.</p>';
    return;
  }

  _umapData = data;

  const trace = {
    x: data.map((d) => d.x),
    y: data.map((d) => d.y),
    z: data.map((d) => d.z),
    mode: "markers+text",
    type: "scatter3d",
    marker: {
      size: data.map((d) => d.type === "knowledge" ? 4 : 6),
      color: data.map((d) => d.type === "knowledge" ? "#008000" : "#000080"),
      opacity: 0.9,
      line: { width: 0.5, color: "#fff" },
    },
    text: data.map((d) => d.name),
    textposition: "top center",
    textfont: { size: 9, color: "#000" },
    hovertemplate: "%{text}<br>%{customdata}<extra></extra>",
    customdata: data.map((d) => `[${d.type}] ${d.description}`),
  };

  const layout = {
    paper_bgcolor: "#c0c0c0",
    scene: {
      bgcolor: "#fff",
      xaxis: { showgrid: true, gridcolor: "#dfdfdf", color: "#000" },
      yaxis: { showgrid: true, gridcolor: "#dfdfdf", color: "#000" },
      zaxis: { showgrid: true, gridcolor: "#dfdfdf", color: "#000" },
      camera: { eye: { x: 1.5, y: 1.5, z: 1.2 } },
    },
    font: { color: "#000" },
    margin: { t: 10, b: 10, l: 10, r: 10 },
  };

  Plotly.newPlot(container, [trace], layout, { responsive: true });
}

// --- Init ---
loadGraph();
loadEmbeddings();
