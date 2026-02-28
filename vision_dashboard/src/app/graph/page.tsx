// @ts-nocheck
"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import Link from "next/link";
import * as d3 from "d3";

export default function GraphPage() {
    const [data, setData] = useState({ nodes: [], links: [] });
    const [loading, setLoading] = useState(true);
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const simulationRef = useRef<any>(null);
    const transformRef = useRef(d3.zoomIdentity);
    const [tooltip, setTooltip] = useState<any>(null);
    const [hoveredNode, setHoveredNode] = useState<any>(null);

    // Fetch data
    useEffect(() => {
        // Limit query to extremely speed up the initial load
        fetch("/api/graph?limit=1500")
            .then(res => res.json())
            .then(json => {
                if (json.success && json.nodes) {
                    setData(json);
                }
                setLoading(false);
            })
            .catch(e => {
                console.error("Failed to load graph", e);
                setLoading(false);
            });
    }, []);

    const nodesRef = useRef<any[]>([]);
    const linksRef = useRef<any[]>([]);

    // 1. Initialize Simulation (Only on data change)
    useEffect(() => {
        if (loading || data.nodes.length === 0 || !canvasRef.current) return;

        const width = window.innerWidth;
        const height = window.innerHeight;

        // Deep copy data for D3 to mutate safely
        nodesRef.current = data.nodes.map(d => ({ ...d }));

        const nodeIds = new Set(nodesRef.current.map(n => n.id));
        linksRef.current = data.links
            .filter(l => nodeIds.has(typeof l.source === 'object' ? l.source.id : l.source) &&
                nodeIds.has(typeof l.target === 'object' ? l.target.id : l.target))
            .map(l => ({ ...l }));

        if (simulationRef.current) simulationRef.current.stop();

        const simulation = d3.forceSimulation(nodesRef.current)
            .force("link", d3.forceLink(linksRef.current).id((d: any) => d.id).distance(d => d.isCategoryLink ? 80 : 40))
            .force("charge", d3.forceManyBody().strength(d => d.isCategory ? -500 : -100))
            .force("center", d3.forceCenter(width / 2, height / 2))
            .force("collide", d3.forceCollide().radius((d: any) => (d.group === "category" ? 18 : 6)))
            .alphaDecay(0.04);

        simulationRef.current = simulation;

        simulation.on("tick", () => {
            // In Canvas, we don't need to do anything here if we draw elsewhere, 
            // but keeping a tick-based render is standard.
            // We'll call an external render function.
            render();
        });

        return () => simulation.stop();
    }, [data, loading]);

    // 2. Rendering Function (Stable, uses refs)
    const render = useCallback(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const ctx = canvas.getContext("2d");
        if (!ctx) return;

        const width = canvas.width / (window.devicePixelRatio || 1);
        const height = canvas.height / (window.devicePixelRatio || 1);
        const transform = transformRef.current;

        ctx.save();
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.translate(transform.x, transform.y);
        ctx.scale(transform.k, transform.k);

        // Draw Links
        ctx.beginPath();
        ctx.strokeStyle = "rgba(255, 255, 255, 0.08)";
        ctx.lineWidth = 0.5;
        linksRef.current.forEach((d: any) => {
            ctx.moveTo(d.source.x, d.source.y);
            ctx.lineTo(d.target.x, d.target.y);
        });
        ctx.stroke();

        // Draw Nodes
        nodesRef.current.forEach((node: any) => {
            const isHovered = hoveredNode?.id === node.id;
            const isCategory = node.group === "category";

            const r = isCategory ? 12 : (isHovered ? 9 : 3.5);

            ctx.beginPath();
            ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);

            if (isCategory) {
                ctx.fillStyle = "#ffffff";
                ctx.fill();
                ctx.lineWidth = 1.6;
                ctx.strokeStyle = "rgba(255,255,255,0.4)";
                ctx.stroke();
            } else {
                ctx.fillStyle = isHovered ? "#00e5ff" : "rgba(255, 255, 255, 0.4)";
                if (isHovered) {
                    ctx.shadowBlur = 20;
                    ctx.shadowColor = "#00e5ff";
                }
                ctx.fill();
                ctx.shadowBlur = 0;
            }

            if (isCategory || transform.k > 2.8 || isHovered) {
                const fontSize = isCategory ? 14 / transform.k : 11 / transform.k;
                ctx.font = `${isCategory ? 600 : 400} ${fontSize}px Inter, sans-serif`;
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.fillStyle = isHovered ? '#00e5ff' : (isCategory ? '#ffffff' : '#aaaaaa');
                const yOffset = isCategory ? 0 : r + fontSize + 2;
                ctx.fillText(node.name || node.id, node.x, node.y + yOffset);
            }
        });

        ctx.restore();
    }, [hoveredNode]);

    // 3. Setup Canvas and Events
    useEffect(() => {
        if (loading || !canvasRef.current) return;

        const canvas = canvasRef.current;
        const width = window.innerWidth;
        const height = window.innerHeight;

        const dpr = window.devicePixelRatio || 1;
        canvas.width = width * dpr;
        canvas.height = height * dpr;
        canvas.style.width = width + "px";
        canvas.style.height = height + "px";
        const ctx = canvas.getContext("2d");
        ctx?.scale(dpr, dpr);

        const zoom = d3.zoom()
            .scaleExtent([0.01, 30])
            .on("zoom", (e) => {
                transformRef.current = e.transform;
                render();
            });

        d3.select(canvas).call(zoom);
        // Remove the forced transition here as it resets state incorrectly
        // d3.select(canvas).transition().duration(1500).call(zoom.transform, d3.zoomIdentity.translate(width / 2, height / 2).scale(0.2).translate(-width / 2, -height / 2));

        // Interaction Handling
        d3.select(canvas).on("mousemove", (e) => {
            const [mx, my] = d3.pointer(e, canvas);
            const simX = transformRef.current.invertX(mx);
            const simY = transformRef.current.invertY(my);

            const radius = 25 / transformRef.current.k;
            let foundNode: any = null;
            let minDistance = radius;

            for (const node of nodesRef.current) {
                const dx = node.x - simX;
                const dy = node.y - simY;
                const dist = Math.sqrt(dx * dx + dy * dy);
                if (dist < minDistance) {
                    minDistance = dist;
                    foundNode = node;
                }
            }

            if (foundNode?.id !== hoveredNode?.id) {
                if (foundNode) {
                    simulationRef.current?.stop();
                } else {
                    simulationRef.current?.alpha(0.01).restart();
                }
                setHoveredNode(foundNode);
                if (foundNode) {
                    setTooltip({ node: foundNode, x: mx, y: my });
                } else {
                    setTooltip(null);
                }
            } else if (foundNode) {
                setTooltip({ node: foundNode, x: mx, y: my });
            }
        });

        d3.select(canvas).on("click", (e) => {
            if (hoveredNode && hoveredNode.filepath && !hoveredNode.isCategory) {
                window.open(`/api/image?path=${encodeURIComponent(hoveredNode.filepath)}`, '_blank');
            }
        });

    }, [loading, render, hoveredNode]);

    return (
        <div style={{ width: "100%", height: "100vh", position: "relative", backgroundColor: "#0a0a0a", overflow: "hidden" }}>
            <div style={{ position: "absolute", zIndex: 10, top: 24, left: 24, padding: "16px", background: "rgba(10,10,10,0.8)", border: "1px solid #333", borderRadius: 8, backdropFilter: "blur(10px)", color: "white" }}>
                <h2 style={{ fontSize: "16px", margin: "0 0 8px 0" }}>Knowledge Nebula</h2>
                <div style={{ fontSize: "12px", color: "#888", marginBottom: "12px" }}>
                    {data.nodes.length} Nodes &middot; {data.links.length} Links
                </div>
                <Link href="/" style={{ color: "white", textDecoration: "underline", fontSize: "13px" }}>&larr; Back to Grid</Link>
            </div>

            {loading ? (
                <div style={{ position: "absolute", top: "50%", left: "50%", transform: "translate(-50%, -50%)", color: "#888" }}>
                    Assembling knowledge dimensions...
                </div>
            ) : (
                <canvas ref={canvasRef} style={{ display: "block" }} />
            )}

            {tooltip && (
                <div style={{
                    position: "absolute",
                    top: Math.min(tooltip.y + 15, window.innerHeight - 350),
                    left: Math.min(tooltip.x + 15, window.innerWidth - 320),
                    pointerEvents: "none",
                    background: "rgba(15, 15, 15, 0.85)",
                    padding: "16px",
                    border: "1px solid rgba(255,255,255,0.1)",
                    borderRadius: "16px",
                    fontFamily: "Inter, sans-serif",
                    fontSize: "12px",
                    width: "300px",
                    color: "white",
                    zIndex: 100,
                    boxShadow: "0 20px 40px rgba(0,0,0,0.6)",
                    backdropFilter: "blur(20px)"
                }}>
                    <div style={{ fontWeight: 800, fontSize: "15px", marginBottom: "12px", color: "#ffffff", letterSpacing: "-0.01em", borderBottom: "1px solid rgba(255,255,255,0.1)", paddingBottom: "8px" }}>
                        {tooltip.node.name || "Unnamed Node"}
                    </div>

                    {tooltip.node.filepath && (
                        <div style={{ width: "100%", height: "180px", overflow: "hidden", borderRadius: "12px", backgroundColor: "#000", marginBottom: "16px", border: "1px solid rgba(255,255,255,0.05)" }}>
                            <img
                                src={`/api/image?path=${encodeURIComponent(tooltip.node.filepath)}&w=350`}
                                style={{ width: "100%", height: "100%", objectFit: "cover" }}
                                alt="preview"
                            />
                        </div>
                    )}

                    <div style={{ marginBottom: "12px" }}>
                        <div style={{ fontSize: "10px", color: "#888", textTransform: "uppercase", marginBottom: "4px", fontWeight: 700 }}>Categories</div>
                        <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
                            {(tooltip.node.tags || "Uncategorized").split(",").map((t: string, i: number) => (
                                <span key={i} style={{ fontSize: "11px", background: "rgba(255,255,255,0.1)", padding: "4px 10px", borderRadius: "6px", color: "#fff" }}>
                                    {t.trim()}
                                </span>
                            ))}
                        </div>
                    </div>

                    {tooltip.node.description && (
                        <div>
                            <div style={{ fontSize: "10px", color: "#888", textTransform: "uppercase", marginBottom: "4px", fontWeight: 700 }}>AI Analysis</div>
                            <div style={{
                                color: "#ddd",
                                fontSize: "12px",
                                lineHeight: "1.6",
                                display: "-webkit-box",
                                WebkitLineClamp: 4,
                                WebkitBoxOrient: "vertical",
                                overflow: "hidden"
                            }}>
                                {tooltip.node.description}
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
