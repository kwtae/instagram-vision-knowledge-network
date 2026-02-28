import os
import io
import json
import base64
import logging
from PIL import Image
from db_manager import db

logger = logging.getLogger("mcp_vision_server.visualize_network")

def generate_graph_html(output_path: str = "network_graph.html", distance_threshold: float = 0.5):
    """
    Extracts documents from ChromaDB, calculates mutual similarities, and builds an interactive D3.js HTML graph simulating Obsidian's graph view.
    """
    try:
        # Fetch all records
        all_data = db.collection.get(include=["documents", "metadatas"])
        
        if not all_data or not all_data["ids"]:
            logger.warning("No records found in ChromaDB to visualize.")
            return None
            
        ids = all_data["ids"]
        metadatas = all_data["metadatas"]
        
        nodes = []
        node_file_map = {} # Maps internal DB ID to display ID
        
        for i, doc_id in enumerate(ids):
            meta = metadatas[i] or {}
            filepath = meta.get("filepath", "Unknown")
            filename = os.path.basename(filepath)
            
            # Form absolute paths for browser linking
            abs_filepath = os.path.abspath(filepath).replace('\\', '/') if filepath != "Unknown" else "Unknown"
            
            # Use filename as label, fallback to ID
            label = filename if filename != "Unknown" else doc_id
            group = meta.get("type", "unknown")
            
            # Generate tiny inline base64 thumbnail for images
            thumbnail_b64 = None
            if group == "image" and os.path.exists(filepath):
                try:
                    with Image.open(filepath) as img:
                        img.thumbnail((64, 64))
                        if img.mode in ("RGBA", "P"):
                            img = img.convert("RGB")
                        buffered = io.BytesIO()
                        img.save(buffered, format="JPEG", quality=50)
                        thumbnail_b64 = "data:image/jpeg;base64," + base64.b64encode(buffered.getvalue()).decode('utf-8')
                except Exception as e:
                    logger.debug(f"Could not generate thumbnail for {filepath}: {e}")
            
            nodes.append({
                "id": doc_id,
                "label": label,
                "group": group,
                "tags": meta.get("tags", ""),
                "filepath": abs_filepath,
                "thumbnail": thumbnail_b64,
                "timestamp": meta.get("timestamp", 0)
            })
            node_file_map[doc_id] = filepath

        edges = []
        
        # Calculate edges based on mutual semantic queries
        # Note: In a dense graph with thousands of items, we'd query by document embeddings
        # Since we use ChromaDB's native collection.query, we iterate using the document vectors
        
        docs = all_data["documents"]
        if not docs:
            return None
        
        # We query the DB for each document to find its nearest neighbors
        results = db.collection.query(
            query_texts=docs,
            n_results=min(len(docs), 10) # limit to top 10 closest per node to avoid visual clutter
        )
        
        for i, query_id in enumerate(ids):
            retrieved_ids = results["ids"][i]
            distances = results["distances"][i]
            
            for j, target_id in enumerate(retrieved_ids):
                dist = distances[j]
                
                # Exclude self and far vectors
                if target_id != query_id and dist < distance_threshold:
                    # Deduplicate undirected edges
                    if query_id < target_id:
                        src, dst = query_id, target_id
                    else:
                        src, dst = target_id, query_id
                        
                    edge = {"source": src, "target": dst, "value": round(1.0 - dist, 3)}
                    if edge not in edges:
                        edges.append(edge)

        # Inject user-defined manual links
        try:
            if os.path.exists("custom_edges.json"):
                with open("custom_edges.json", "r", encoding="utf-8") as f:
                    custom = json.load(f)
                    for c_edge in custom:
                        edge = {"source": c_edge["source"], "target": c_edge["target"], "value": 0.99, "isCustom": True}
                        edges.append(edge)
        except Exception as e:
            logger.warning(f"Could not load custom_edges.json: {e}")

        # Build visualizer HTML template using D3.js force simulation
        html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>MCP Vision Network Graph</title>
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <style>
        :root {{
            --bg-color: #0d1117;
            --grid-color: rgba(255, 255, 255, 0.03);
            --border-color: rgba(255, 255, 255, 0.1);
            --glass-bg: rgba(20, 24, 34, 0.65);
            --glass-border: rgba(255, 255, 255, 0.08);
            --text-normal: #e0e6ed;
            --text-muted: #8b949e;
            --accent-color: #ffffff;
            --accent-hover: #cccccc;
            --btn-bg: rgba(255, 255, 255, 0.05);
            --btn-hover: rgba(255, 255, 255, 0.1);
        }}
        body {{
            margin: 0;
            background-color: var(--bg-color);
            background-image: radial-gradient(var(--grid-color) 1px, transparent 1px);
            background-size: 30px 30px;
            color: var(--text-normal);
            font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
            overflow: hidden;
        }}
        svg {{ width: 100vw; height: 100vh; }}
        
        #toolbar {{
            position: absolute; top: 24px; left: 24px; z-index: 5;
            display: flex; flex-direction: column; width: 300px;
            background: var(--glass-bg); backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);
            border: 1px solid var(--glass-border); border-radius: 16px;
            box-shadow: 0 12px 32px rgba(0, 0, 0, 0.4); overflow: hidden;
            transition: all 0.3s cubic-bezier(0.2, 0.8, 0.2, 1);
        }}
        .toolbar-header {{ padding: 20px; border-bottom: 1px solid var(--border-color); }}
        .toolbar-header h2 {{ margin: 0; font-size: 16px; font-weight: 600; letter-spacing: -0.5px; color: #ffffff; display: flex; align-items: center; gap: 8px; }}
        .toolbar-header p {{ margin: 8px 0 0 0; font-size: 11px; color: var(--text-muted); }}
        .toolbar-search {{ padding: 16px 20px; border-bottom: 1px solid var(--border-color); }}
        #searchInput {{
            width: 100%; padding: 10px 14px; background: rgba(0, 0, 0, 0.2);
            color: var(--text-normal); border: 1px solid var(--border-color); border-radius: 8px; 
            font-size: 13px; outline: none; transition: all 0.2s ease; box-sizing: border-box;
        }}
        #searchInput:focus {{ background: rgba(0, 0, 0, 0.4); border-color: var(--accent-color); box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.2); }}
        #searchInput::placeholder {{ color: #6e7681; }}
        
        .toolbar-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; padding: 20px; }}
        button {{
            width: 100%; padding: 10px 12px; background: var(--btn-bg); color: var(--text-normal); 
            border: 1px solid var(--glass-border); border-radius: 8px; font-size: 12px; cursor: pointer; 
            transition: all 0.2s; font-weight: 500; display: flex; align-items: center; justify-content: center; gap: 6px;
        }}
        button:hover {{ background: var(--btn-hover); border-color: #555; color: #fff; }}
        .action-primary {{ grid-column: span 2; background: rgba(255, 255, 255, 0.1); color: var(--accent-color); border-color: rgba(255, 255, 255, 0.2); }}
        .action-primary:hover {{ background: rgba(255, 255, 255, 0.2); color: var(--accent-hover); border-color: rgba(255, 255, 255, 0.4); }}

        #tooltip {{
            position: absolute; background: rgba(20, 24, 34, 0.95); backdrop-filter: blur(12px);
            padding: 16px; border-radius: 12px; font-size: 12px; color: var(--text-normal);
            pointer-events: none; display: none; max-width: 280px; z-index: 10;
            border: 1px solid var(--glass-border); box-shadow: 0 12px 32px rgba(0,0,0,0.5); line-height: 1.6; font-family: inherit;
        }}
        #tooltip strong {{ color: #fff; font-weight: 500; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; opacity: 0.7; display: block; margin-bottom: 2px; }}
        
        #chatbot {{
            position: absolute; right: 24px; bottom: 24px; width: 360px; height: 500px;
            background: var(--glass-bg); backdrop-filter: blur(16px);
            border: 1px solid var(--glass-border); border-radius: 16px; display: flex; flex-direction: column; 
            box-shadow: 0 12px 40px rgba(0,0,0,0.5); z-index: 10; overflow: hidden; font-family: inherit; font-size: 13px;
        }}
        #chatHeader {{ padding: 16px; background: rgba(0,0,0,0.2); font-weight: 600; border-bottom: 1px solid var(--border-color); text-align: left; display: flex; align-items: center; gap: 8px; }}
        #chatHeader::before {{ content: "✦"; color: var(--accent-color); }}
        #chatMessages {{ flex: 1; padding: 16px; overflow-y: auto; display: flex; flex-direction: column; gap: 12px; }}
        .msg {{ padding: 10px 14px; border-radius: 10px; max-width: 85%; line-height: 1.5; word-wrap: break-word; }}
        .msg-user {{ align-self: flex-end; background: var(--accent-color); color: #fff; border-bottom-right-radius: 2px; }}
        .msg-bot {{ align-self: flex-start; background: rgba(255,255,255,0.05); border: 1px solid var(--glass-border); color: #e0e6ed; border-bottom-left-radius: 2px; }}
        #chatInputContainer {{ display: flex; padding: 12px 16px; border-top: 1px solid var(--border-color); background: rgba(0,0,0,0.2); }}
        #chatInput {{ flex: 1; padding: 10px 14px; border: 1px solid var(--glass-border); border-radius: 8px; outline: none; font-family: inherit; background: rgba(0,0,0,0.3); color: #fff; box-sizing: border-box; }}
        #chatInput:focus {{ border-color: var(--accent-color); }}
        #chatSend {{ margin-left: 8px; padding: 10px 16px; background: var(--accent-color); color: #fff; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; font-family: inherit; transition: background 0.2s; }}
        #chatSend:hover {{ background: var(--accent-hover); }}
    </style>
</head>
<body>
    <div id="toolbar">
        <div class="toolbar-header">
            <h2>Graph Explorer</h2>
            <p>{len(nodes)} Nodes · {len(edges)} Edges</p>
        </div>
        <div class="toolbar-search">
            <input type="text" id="searchInput" placeholder="Search visual network..."/>
        </div>
        <div class="toolbar-grid">
            <button id="toggleTimeline" class="action-primary">⏱ Timeline Mode</button>
            <button onclick="alert('Click a node to open file.\\nRight-click to edit tags.\\nShift+Click two nodes to link manually.')">ℹ️ Help</button>
            <button onclick="simulation.alpha(1).restart()">🔄 Refresh Layout</button>
        </div>
    </div>
    <div id="tooltip"></div>
    <div id="chatbot">
        <div id="chatHeader">로컬 지식 비서</div>
        <div id="chatMessages">
            <div class="msg msg-bot">네트워크 데이터베이스 안에서 무엇을 찾아드릴까요?</div>
        </div>
        <div id="chatInputContainer">
            <input type="text" id="chatInput" placeholder="질문 입력..." onkeypress="if(event.key==='Enter') sendChat()"/>
            <button id="chatSend" onclick="sendChat()">전송</button>
        </div>
    </div>
    <svg>
        <defs>
            <clipPath id="circle-clip">
                <circle r="12"></circle>
            </clipPath>
        </defs>
        <g class="container"></g>
    </svg>
    <script>
        const graph = {json.dumps({"nodes": nodes, "links": edges})};
        
        const width = window.innerWidth;
        const height = window.innerHeight;

        const svg = d3.select("svg");
        const tooltip = d3.select("#tooltip");

        // Assign primary semantic tag
        graph.nodes.forEach(d => {{
            d.primaryTag = d.tags ? d.tags.split(',')[0].trim() : '미분류';
            d.isCategory = false;
        }});

        // Generate Category Hub Nodes
        const categories = Array.from(new Set(graph.nodes.map(d => d.primaryTag)));
        categories.forEach((cat, i) => {{
            graph.nodes.push({{
                id: "CAT_" + cat,
                label: cat,
                primaryTag: cat,
                group: "category",
                isCategory: true,
                tags: cat,
                degree: 0,
                thumbnail: null
            }});
        }});

        // Connect files to their category hubs
        graph.nodes.filter(n => !n.isCategory).forEach(n => {{
            graph.links.push({{
                source: n.id,
                target: "CAT_" + n.primaryTag,
                value: 1,
                isCategoryLink: true
            }});
        }});

        // Calculate degree centrality
        const degreeMap = {{}};
        graph.links.forEach(l => {{
            let src = l.source.id || l.source;
            let tgt = l.target.id || l.target;
            degreeMap[src] = (degreeMap[src] || 0) + 1;
            degreeMap[tgt] = (degreeMap[tgt] || 0) + 1;
        }});
        graph.nodes.forEach(n => {{
            n.degree = degreeMap[n.id] || 0;
        }});
        
        const maxCatDegree = d3.max(graph.nodes.filter(n => n.isCategory), d => d.degree) || 1;

        // Visual rules inspired by Obsidian
        function getNodeRadius(d) {{
            if(d.isCategory) return 14 + (d.degree / maxCatDegree) * 22; // Big hubs
            return 4 + Math.min(d.degree, 10) * 0.5; // Small flat files
        }}

        const simulation = d3.forceSimulation(graph.nodes)
            .force("link", d3.forceLink(graph.links).id(d => d.id).distance(d => d.isCategoryLink ? 160 : 300).strength(d => d.isCategoryLink ? 0.7 : 0.02))
            .force("charge", d3.forceManyBody().strength(d => d.isCategory ? -1500 : -100))
            .force("center", d3.forceCenter(width / 2, height / 2))
            .force("collide", d3.forceCollide().radius(d => getNodeRadius(d) + 20).iterations(3));

        // Grayscale hierarchy palette
        const customColors = ["#ffffff", "#f0f0f0", "#e0e0e0", "#d0d0d0", "#cccccc", "#bcbcbc", "#aaaaaa", "#999999", "#888888", "#777777"];
        const colorScale = d3.scaleOrdinal(customColors);

        const container = svg.select(".container");

        const link = container.append("g")
            .attr("class", "links")
            .selectAll("line")
            .data(graph.links)
            .enter().append("line")
            .attr("class", "link")
            .attr("stroke", d => d.isCustom ? "#ffffff" : (d.isCategoryLink ? "rgba(255,255,255,0.15)" : "rgba(255,255,255,0.05)"))
            .attr("stroke-width", d => d.isCustom ? 2.0 : (d.isCategoryLink ? 1.5 : 0.8))
            .attr("stroke-dasharray", d => d.isCustom ? "4,4" : "none")
            .attr("stroke-opacity", d => d.isCustom ? 1.0 : (d.isCategoryLink ? 0.8 : 0.4));

        const node = container.append("g")
            .attr("class", "nodes")
            .selectAll("g")
            .data(graph.nodes)
            .enter().append("g")
            .attr("class", "node")
            .call(d3.drag()
                .on("start", dragstarted)
                .on("drag", dragged)
                .on("end", dragended));

        node.append("circle")
            .attr("r", d => getNodeRadius(d))
            .attr("fill", d => d.isCategory ? "#ffffff" : d3.color("#ffffff").darker(d.degree > 3 ? 1.5 : 3.0)) // Highlight high-degree files naturally
            .attr("opacity", d => d.isCategory ? 1.0 : 0.8)
            .attr("stroke", d => d.isCategory ? "#ffffff" : "none")
            .attr("stroke-width", d => d.isCategory ? "2px" : "0")
            .style("filter", d => d.isCategory ? `drop-shadow(0 0 16px rgba(255,255,255,0.6))` : "none");

        // Clean Obsidian Labels + Galaxy Naming
        node.append("text")
            .attr("text-anchor", d => d.isCategory ? "middle" : "start")
            .attr("alignment-baseline", d => d.isCategory ? "central" : "auto")
            .attr("dx", d => d.isCategory ? 0 : getNodeRadius(d) + 8)
            .attr("dy", d => d.isCategory ? 0 : ".35em")
            .style("fill", d => d.isCategory ? "#000000" : "#a0a0a0")
            .style("font-size", d => d.isCategory ? "16px" : "11px")
            .style("font-weight", d => d.isCategory ? "800" : "500")
            .style("letter-spacing", d => d.isCategory ? "1px" : "0.5px")
            .style("opacity", d => d.isCategory ? 1.0 : 0) // Hide file labels by default
            .text(d => d.isCategory ? d.label.toUpperCase() : (d.label.length > 20 ? d.label.substring(0,20)+"..." : d.label));

        // Search filtering
        d3.select("#searchInput").on("input", function() {{
            const term = this.value.toLowerCase().trim();
            if(!term) {{
                node.style("opacity", 1);
                link.style("opacity", d => d.isCategoryLink ? 0.8 : 0.4);
            }} else {{
                node.style("opacity", d => {{
                    const tags = d.tags ? d.tags.toLowerCase() : "";
                    const label = d.label ? d.label.toLowerCase() : "";
                    return (tags.includes(term) || label.includes(term)) ? 1 : 0.05;
                }});
                link.style("opacity", 0.02);
            }}
        }});

        // Timeline toggle
        let isTimeline = false;
        d3.select("#toggleTimeline").on("click", function() {{
            isTimeline = !isTimeline;
            if(isTimeline) {{
                const ext = d3.extent(graph.nodes.filter(n=>!n.isCategory), d => d.timestamp);
                const tScale = d3.scaleTime().domain(ext).range([100, width - 100]);
                
                simulation.force("x", d3.forceX(d => d.isCategory ? width/2 : tScale(d.timestamp)).strength(0.8))
                          .force("y", d3.forceY(height/2).strength(0.3))
                          .force("charge", d3.forceManyBody().strength(-30))
                          .force("collide", d3.forceCollide().radius(d => getNodeRadius(d) + 2));
                          
                d3.select(this).text("🌌 Nebula View").style("background", "rgba(255, 255, 255, 0.1)").style("color", "#fff").style("border-color", "rgba(255, 255, 255, 0.2)");
            }} else {{
                simulation.force("x", d3.forceX(width/2).strength(0.05))
                          .force("y", d3.forceY(height/2).strength(0.05))
                          .force("charge", d3.forceManyBody().strength(d => d.isCategory ? -900 : -50))
                          .force("collide", d3.forceCollide().radius(d => getNodeRadius(d) + 5));
                          
                d3.select(this).text("⏱ Timeline Mode").style("background", "rgba(255, 255, 255, 0.1)").style("color", "#aaa").style("border-color", "rgba(255, 255, 255, 0.2)");
            }}
            simulation.alpha(1).restart();
        }});

        // Hover & Tooltip Events
        node.on("mouseover", function(event, d) {{
                // Highlight connected links
                link.style("stroke", l => (l.source.id === d.id || l.target.id === d.id) ? "#ffffff" : (l.isCategoryLink ? "rgba(255,255,255,0.15)" : "rgba(255,255,255,0.05)"))
                    .style("stroke-opacity", l => (l.source.id === d.id || l.target.id === d.id) ? 1 : 0.05);

                // Highlight node and show label
                d3.select(this).select("circle").attr("stroke", "#ffffff").attr("stroke-width", "2px").attr("opacity", 1);
                d3.select(this).select("text").style("opacity", 1).style("fill", "#ffffff").style("text-shadow", `0 2px 8px rgba(255,255,255,0.8)`);

                let thumbHtml = d.thumbnail ? `<br/><img src="${{d.thumbnail}}" style="border-radius:6px; max-width:120px; margin-top:8px; border: 1px solid rgba(255,255,255,0.1);">` : "";
                
                tooltip.style("display", "block")
                    .html(`<strong>${{d.isCategory ? 'Category' : 'File'}}</strong> ${{d.label}}<br/><span style="color:#aaa; font-size:10px;">Tags: ${{d.tags}}</span>${{!d.isCategory ? '<br/><span style="color:#888; font-size:10px;">우클릭하여 태그 편집</span>' : ''}}${{thumbHtml}}`)
                    .style("left", (event.pageX + 15) + "px")
                    .style("top", (event.pageY + 15) + "px");
            }})
            .on("mouseout", function(event, d) {{
                // Reset links
                link.style("stroke", l => l.isCustom ? "#ffffff" : (l.isCategoryLink ? "rgba(255,255,255,0.15)" : "rgba(255,255,255,0.05)"))
                    .style("stroke-opacity", l => l.isCustom ? 1.0 : (l.isCategoryLink ? 0.8 : 0.4));

                // Reset node
                if(window.selectedSourceNode && d.id === window.selectedSourceNode.id) return; // Keep selection highlighted
                d3.select(this).select("circle")
                    .attr("stroke", n => n.isCategory ? "#ffffff" : "none")
                    .attr("stroke-width", n => n.isCategory ? "2px" : "0")
                    .attr("opacity", n => n.isCategory ? 1.0 : 0.8);
                d3.select(this).select("text")
                    .style("opacity", n => n.isCategory ? 1.0 : 0)
                    .style("fill", n => n.isCategory ? "#000000" : "#a0a0a0")
                    .style("text-shadow", "none");
                
                tooltip.style("display", "none");
            }})
            .on("click", function(event, d) {{
                if(d.isCategory) return;
                
                if(event.shiftKey) {{
                    if(!window.selectedSourceNode) {{
                        window.selectedSourceNode = d;
                        d3.select(this).select("circle").attr("stroke", "#ff6b81").attr("stroke-width", "3px");
                        alert(`소스 노드를 선택했습니다: ${{d.label}}\\n연결하려는 다른 노드를 Shift+Click 하세요.`);
                    }} else {{
                        const targetNode = d;
                        if(targetNode.id !== window.selectedSourceNode.id) {{
                            fetch(`http://localhost:8080/api/link`, {{
                                method: "POST",
                                headers: {{ "Content-Type": "application/json" }},
                                body: JSON.stringify({{ source: window.selectedSourceNode.id, target: targetNode.id }})
                            }})
                            .then(res => res.json())
                            .then(data => {{
                                if(data.success) {{
                                    alert("두 노드가 성공적으로 연결되었습니다.");
                                }}
                            }})
                            .catch(err => alert("DB 동기화 서버가 응답하지 않습니다."));
                        }}
                        // Reset selection
                        window.selectedSourceNode = null;
                        node.select("circle").attr("stroke", n => n.isCategory ? d3.color(colorScale(n.primaryTag)).darker(0.3) : "none").attr("stroke-width", n => n.isCategory ? "1.5px" : "0");
                    }}
                    return;
                }}

                if(d.filepath && d.filepath !== "Unknown") {{
                    fetch(`http://localhost:8080/api/open`, {{
                        method: "POST",
                        headers: {{ "Content-Type": "application/json" }},
                        body: JSON.stringify({{ filepath: d.filepath }})
                    }})
                    .catch(err => alert("파일을 여는 중 서버 오류가 발생했습니다. (보안 정책 등으로 차단될 수 있음)"));
                }} else {{
                    alert("파일 경로를 찾을 수 없습니다.");
                }}
            }})
            .on("contextmenu", function(event, d) {{
                event.preventDefault();
                if(d.isCategory) return;
                const newTags = prompt("태그를 수정합니다 (쉽표 반점 구분):\\n여러 카테고리를 자유롭게 편집하세요.", d.tags);
                if (newTags !== null && newTags.trim() !== "") {{
                    d.tags = newTags;
                    fetch(`http://localhost:8080/api/update`, {{
                        method: "POST",
                        headers: {{ "Content-Type": "application/json" }},
                        body: JSON.stringify({{ id: d.id, tags: newTags }})
                    }})
                    .then(res => res.json())
                    .then(data => {{
                        if(data.success) alert("태그가 실시간으로 DB에 반영되었습니다.");
                    }})
                    .catch(err => alert("DB 동기화 서버가 응답하지 않습니다."));
                }}
            }});

        // Zoom and Pan
        const zoom = d3.zoom()
            .scaleExtent([0.1, 4])
            .on("zoom", (event) => {{
                container.attr('transform', event.transform);
            }});
        svg.call(zoom);

        simulation.on("tick", () => {{
            link.attr("x1", d => d.source.x)
                .attr("y1", d => d.source.y)
                .attr("x2", d => d.target.x)
                .attr("y2", d => d.target.y);

            node.attr("transform", d => `translate(${{d.x}},${{d.y}})`);
        }});

        function dragstarted(event, d) {{
            if (!event.active) simulation.alphaTarget(0.3).restart();
            d.fx = d.x;
            d.fy = d.y;
        }}

        function dragged(event, d) {{
            d.fx = event.x;
            d.fy = event.y;
        }}

        function dragended(event, d) {{
            if (!event.active) simulation.alphaTarget(0);
            // Sticky nodes: Intentionally NOT resetting d.fx/d.fy so manual clustering is saved per session
        }}

        async function sendChat() {{
            const input = document.getElementById("chatInput");
            const container = document.getElementById("chatMessages");
            const text = input.value.trim();
            if(!text) return;
            
            container.innerHTML += `<div class="msg msg-user">${{text}}</div>`;
            input.value = "";
            const loadingId = "loading" + Date.now();
            container.innerHTML += `<div class="msg msg-bot" id="${{loadingId}}">로컬 DB 탐색 중...</div>`;
            container.scrollTop = container.scrollHeight;
            
            try {{
                const res = await fetch("http://localhost:8080/api/chat", {{
                    method: "POST",
                    headers: {{"Content-Type": "application/json"}},
                    body: JSON.stringify({{query: text}})
                }});
                const data = await res.json();
                document.getElementById(loadingId).remove();
                
                // Markdown or simple line breaks
                const formattedRes = (data.response || "결과를 찾을 수 없습니다.").replace(/\\n/g, '<br/>');
                container.innerHTML += `<div class="msg msg-bot">${{formattedRes}}</div>`;
                container.scrollTop = container.scrollHeight;
            }} catch(e) {{
                if(document.getElementById(loadingId)) document.getElementById(loadingId).remove();
                container.innerHTML += `<div class="msg msg-bot" style="color:red">통신 오류가 발생했습니다. AI 서버가 켜져있는지 확인하세요.</div>`;
            }}
        }}
    </script>
</body>
</html>"""
        
        full_path = os.path.abspath(output_path)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(html_template)
            
        logger.info(f"Generated network graph visualization at: {full_path}")
        return full_path
    
    except Exception as e:
        logger.error(f"Failed to generate network visualization: {e}")
        return None

import http.server
import socketserver
import threading

class GraphRequestHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/' or self.path == '/network_graph.html':
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            with open("network_graph.html", "rb") as f:
                self.wfile.write(f.read())
        else:
            super().do_GET()
            
    def do_OPTIONS(self):
        self.send_response(200, "ok")
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header("Access-Control-Allow-Headers", "X-Requested-With, Content-Type")
        self.end_headers()

    def do_POST(self):
        if self.path == '/api/update':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            from db_manager import db # Ensure db is fresh
            
            try:
                data = json.loads(post_data)
                file_id = data.get("id")
                new_tags = data.get("tags")
                
                success = False
                if file_id and new_tags:
                    success = db.update_tags(file_id, new_tags)
                    if success:
                        generate_graph_html() # Background update HTML
                        
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({"success": success}).encode())
                return
            except Exception as e:
                logger.error(f"POST Update Error: {e}")
                self.send_response(500)
                self.end_headers()
                
        elif self.path == '/api/link':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            try:
                data = json.loads(post_data)
                source = data.get("source")
                target = data.get("target")
                
                success = False
                if source and target:
                    # Append to custom_edges.json persistently
                    custom_edges = []
                    ce_file = "custom_edges.json"
                    if os.path.exists(ce_file):
                        with open(ce_file, "r", encoding="utf-8") as f:
                            custom_edges = json.load(f)
                            
                    custom_edges.append({"source": source, "target": target})
                    
                    with open(ce_file, "w", encoding="utf-8") as f:
                        json.dump(custom_edges, f)
                        
                    success = True
                    generate_graph_html() # Rebuild D3 file behind the scenes
                        
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({"success": success}).encode())
                return
            except Exception as e:
                logger.error(f"POST Link Error: {e}")
                self.send_response(500)
                self.end_headers()

        elif self.path == '/api/open':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            try:
                data = json.loads(post_data)
                filepath = data.get("filepath")
                if filepath and os.path.exists(filepath):
                    # Use OS default handler to open the file
                    os.startfile(filepath)
                
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({"success": True}).encode())
                return
            except Exception as e:
                logger.error(f"POST Open Error: {e}")
                self.send_response(500)
                self.end_headers()

        elif self.path == '/api/chat':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            from db_manager import db
            import requests
            try:
                data = json.loads(post_data)
                query = data.get("query", "")
                
                results = db.search_similar(query, n_results=5)
                context_str = ""
                if results:
                    docs = []
                    for r in results:
                        docs.append(f"태그: {r['metadata'].get('tags', '')}\n경로: {r['metadata'].get('filepath', '')}")
                    context_str = "\n\n".join(docs)
                
                if context_str:
                    prompt = f"당신은 스마트한 개인 지식 비서입니다. 아래의 정보 추출 결과를 바탕으로 사용자의 질문에 한국어로 친절하고 전문적으로 대답하세요. 파일 경로가 있으면 레퍼런스로 같이 언급하세요.\n\n[데이터베이스 검색 결과]\n{context_str}\n\n[사용자 질문]\n{query}"
                else:
                    prompt = f"사용자 질문: {query}\n현재 연관된 파일이 부족합니다. 있는 지식 한도 내에서 대답하되 정보가 부족함을 알리세요."
                
                url = "http://localhost:11434/api/generate"
                payload = {
                    "model": "llava:7b",
                    "prompt": prompt,
                    "stream": False
                }
                response = requests.post(url, json=payload, timeout=60)
                response.raise_for_status()
                ans = response.json().get("response", "")
                
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({"response": ans}).encode('utf-8'))
                return
            except Exception as e:
                logger.error(f"POST Chat Error: {e}")
                self.send_response(500)
                self.end_headers()
                
        else:
            self.send_response(404)
            self.end_headers()

def run_server(port=8080):
    Handler = GraphRequestHandler
    try:
        with socketserver.TCPServer(("", port), Handler) as httpd:
            logger.info(f"Serving Graph UI and API on http://localhost:{port}")
            httpd.serve_forever()
    except OSError:
        logger.error(f"Port {port} is already in use. Please close the existing server.")

if __name__ == "__main__":
    generate_graph_html()
    run_server()
