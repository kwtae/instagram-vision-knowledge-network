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
            --bg-color: #fdfdfd;
            --grid-color: rgba(0, 0, 0, 0.03);
            --border-color: #e5e5e5;
            --text-normal: #333333;
            --text-muted: #888888;
            --accent-color: #bbbbbb;
        }}
        body {{
            margin: 0;
            background-color: var(--bg-color);
            background-image: 
                linear-gradient(var(--grid-color) 1px, transparent 1px),
                linear-gradient(90deg, var(--grid-color) 1px, transparent 1px);
            background-size: 30px 30px;
            color: var(--text-normal);
            font-family: -apple-system, BlinkMacSystemFont, "Helvetica Neue", "Helvetica", "Noto Sans KR", "Noto Sans", sans-serif;
            overflow: hidden;
        }}
        svg {{ width: 100vw; height: 100vh; }}
        #toolbar {{
            position: absolute;
            top: 24px;
            left: 24px;
            z-index: 5;
            display: flex;
            flex-direction: column;
            gap: 8px;
            width: 260px;
        }}
        #searchInput {{
            width: 100%; padding: 12px 16px; background: rgba(255, 255, 255, 0.85);
            backdrop-filter: blur(12px); color: var(--text-normal); 
            border: 1px solid var(--border-color); border-radius: 8px; 
            font-size: 13px; outline: none; box-shadow: 0 4px 12px rgba(0,0,0,0.04);
            transition: all 0.2s; font-family: inherit;
        }}
        #searchInput:focus {{ background: #fff; border-color: #aaa; box-shadow: 0 6px 16px rgba(0,0,0,0.08); }}
        #searchInput::placeholder {{ color: #aaa; }}
        
        .toolbar-extras {{
            opacity: 0;
            transform: translateY(-5px);
            pointer-events: none;
            transition: all 0.3s cubic-bezier(0.2, 0.8, 0.2, 1);
            background: rgba(255, 255, 255, 0.85);
            backdrop-filter: blur(12px);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 12px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.04);
        }}
        #toolbar:hover .toolbar-extras {{
            opacity: 1;
            transform: translateY(0);
            pointer-events: auto;
        }}
        .toolbar-extras p {{ margin: 0 0 10px 0; font-size: 11px; color: var(--text-muted); line-height: 1.5; }}
        button {{
            width: 100%; padding: 8px; background: #f5f5f5; color: var(--text-normal); 
            border: 1px solid var(--border-color); border-radius: 6px; font-size: 12px; 
            cursor: pointer; transition: all 0.2s; font-family: inherit; font-weight: 500;
        }}
        button:hover {{ background: #eaeaea; }}
        .link {{ stroke: #ccc; stroke-opacity: 0.4; stroke-width: 1px; }}
        .node text {{ pointer-events: none; text-shadow: 0 1px 3px rgba(255,255,255,0.8); }}
        #tooltip {{
            position: absolute; background: rgba(255, 255, 255, 0.95); backdrop-filter: blur(8px);
            padding: 12px; border-radius: 8px; font-size: 12px; color: var(--text-normal);
            pointer-events: none; display: none; max-width: 280px; z-index: 10;
            border: 1px solid var(--border-color); box-shadow: 0 8px 24px rgba(0,0,0,0.08);
            line-height: 1.5; font-family: inherit;
        }}
        #tooltip strong {{ color: #111; font-weight: 600; }}
    </style>
</head>
<body>
    <div id="toolbar">
        <input type="text" id="searchInput" placeholder="Search... (Hover for menu)"/>
        <div class="toolbar-extras">
            <p>Nodes: {len(nodes)} | Edges: {len(edges)}<br/>* Click: Open File<br/>* Right Click: Edit Tags<br/>* Shift+Click (Two Nodes): Connect Manually</p>
            <button id="toggleTimeline">Timeline Mode</button>
        </div>
    </div>
    <div id="tooltip"></div>
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

        // Modern Japanese minimalist colors (Sumi, Sakura, Moegi, Rikyucha, Yamabuki, Sora, Fuji, etc)
        const customColors = ["#899b9e", "#d89e9e", "#86a982", "#bba785", "#70899c", "#b695a5", "#a7a17a", "#738b81", "#cca598", "#888888"];
        const colorScale = d3.scaleOrdinal(customColors);

        const container = svg.select(".container");

        const link = container.append("g")
            .attr("class", "links")
            .selectAll("line")
            .data(graph.links)
            .enter().append("line")
            .attr("class", "link")
            .attr("stroke", d => d.isCustom ? "#ff6b81" : (d.isCategoryLink ? "#d8d8d8" : "#ebebeb"))
            .attr("stroke-width", d => d.isCustom ? 2.0 : (d.isCategoryLink ? 1.0 : 0.4))
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
            .attr("fill", d => d.isCategory ? colorScale(d.primaryTag) : d3.color(colorScale(d.primaryTag)).brighter(0.4))
            .attr("opacity", d => d.isCategory ? 0.95 : 0.8)
            .attr("stroke", d => d.isCategory ? d3.color(colorScale(d.primaryTag)).darker(0.3) : "none")
            .attr("stroke-width", d => d.isCategory ? "1.5px" : "0");

        // Clean Obsidian Labels
        node.append("text")
            .attr("dx", d => getNodeRadius(d) + 8)
            .attr("dy", ".35em")
            .style("fill", d => d.isCategory ? d3.color(colorScale(d.primaryTag)).darker(0.6) : "#999")
            .style("font-size", d => d.isCategory ? "16px" : "11px")
            .style("font-weight", d => d.isCategory ? "600" : "normal")
            .style("opacity", d => d.isCategory ? 1 : 0) // Hide file labels initially to prevent mess
            .text(d => d.isCategory ? d.label : (d.label.length > 20 ? d.label.substring(0,20)+"..." : d.label));

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
                          
                d3.select(this).text("🌌 별자리 모드 전환").style("background", "#ff6b6b");
            }} else {{
                simulation.force("x", d3.forceX(width/2).strength(0.05))
                          .force("y", d3.forceY(height/2).strength(0.05))
                          .force("charge", d3.forceManyBody().strength(d => d.isCategory ? -900 : -50))
                          .force("collide", d3.forceCollide().radius(d => getNodeRadius(d) + 5));
                          
                d3.select(this).text("Timeline Mode").style("background", "#4db8ff").style("color", "#000");
            }}
            simulation.alpha(1).restart();
        }});

        // Hover & Tooltip Events
        node.on("mouseover", function(event, d) {{
                // Highlight connected links
                link.style("stroke", l => (l.source.id === d.id || l.target.id === d.id) ? colorScale(d.primaryTag) : (l.isCategoryLink ? "#d8d8d8" : "#ebebeb"))
                    .style("stroke-opacity", l => (l.source.id === d.id || l.target.id === d.id) ? 1 : 0.1);

                // Highlight node and show label
                d3.select(this).select("circle").attr("stroke", "#444").attr("stroke-width", "2px");
                d3.select(this).select("text").style("opacity", 1).style("fill", "#222");

                let thumbHtml = d.thumbnail ? `<br/><img src="${{d.thumbnail}}" style="border-radius:6px; max-width:80px; margin-top:8px; border: 1px solid #ddd;">` : "";
                
                tooltip.style("display", "block")
                    .html(`<strong>${{d.isCategory ? 'Category' : 'File'}}:</strong> ${{d.label}}<br/><strong>Tags:</strong> ${{d.tags}}${{!d.isCategory ? '<br/><em>우클릭하여 태그 편집</em>' : ''}}${{thumbHtml}}`)
                    .style("left", (event.pageX + 15) + "px")
                    .style("top", (event.pageY + 15) + "px");
            }})
            .on("mouseout", function(event, d) {{
                // Reset links
                link.style("stroke", l => l.isCustom ? "#ff6b81" : (l.isCategoryLink ? "#d8d8d8" : "#ebebeb"))
                    .style("stroke-opacity", l => l.isCustom ? 1.0 : (l.isCategoryLink ? 0.8 : 0.4));

                // Reset node
                if(window.selectedSourceNode && d.id === window.selectedSourceNode.id) return; // Keep selection highlighted
                d3.select(this).select("circle").attr("stroke", n => n.isCategory ? d3.color(colorScale(n.primaryTag)).darker(0.3) : "none").attr("stroke-width", n => n.isCategory ? "1.5px" : "0");
                d3.select(this).select("text").style("opacity", n => n.isCategory ? 1 : 0).style("fill", n => n.isCategory ? d3.color(colorScale(n.primaryTag)).darker(0.6) : "#999");
                
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
                    window.open('file:///' + d.filepath, '_blank');
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
