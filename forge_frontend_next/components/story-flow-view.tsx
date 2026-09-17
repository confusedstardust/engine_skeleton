"use client";

import { useMemo, useState } from "react";
import { ReactFlow, Background, Controls, Handle, Position, MarkerType, type NodeProps, type Node, type Edge } from "@xyflow/react";
import dagre from "@dagrejs/dagre";
import type { StoryGraph } from "./story-graph-data";

type StoryNode = Node<{ label: string; kind: string; order: number }, "story">;
function StoryCard({ data }: NodeProps<StoryNode>) {
  return <div className={`story-flow-card ${data.kind}`} title={data.label}>
    <Handle type="target" position={Position.Left} />
    <span className="story-flow-card-meta">{data.kind === "start" ? "故事起点" : data.kind === "ending" ? "故事结局" : data.kind === "missing" ? "目标缺失" : "剧情场景"}<i>{String(data.order).padStart(2, "0")}</i></span>
    <strong>{data.label}</strong>
    <Handle type="source" position={Position.Right} />
  </div>;
}
const nodeTypes = { story: StoryCard };

export function StoryFlowView({ graph }: { graph: StoryGraph }) {
  const [optionText, setOptionText] = useState("");
  const { nodes, edges } = useMemo(() => {
    const layout = new dagre.graphlib.Graph({ multigraph: true });
    layout.setGraph({ rankdir: "LR", nodesep: 48, ranksep: 145, marginx: 32, marginy: 32 });
    layout.setDefaultEdgeLabel(() => ({}));
    graph.nodes.forEach(node => layout.setNode(node.id, { width: 200, height: 100 }));
    graph.edges.forEach(edge => layout.setEdge(edge.source, edge.target, {}, edge.id));
    dagre.layout(layout);
    const nodes: StoryNode[] = graph.nodes.map((node, index) => {
      const point = layout.node(node.id);
      return { id: node.id, type: "story", position: { x: point.x - 100, y: point.y - 50 }, data: { label: node.label, kind: node.kind, order: index + 1 } };
    });
    const edges: Edge[] = graph.edges.map(edge => ({
      ...edge, type: "smoothstep", label: edge.label.length > 16 ? `${edge.label.slice(0, 16)}…` : edge.label,
      interactionWidth: 24, markerEnd: { type: MarkerType.ArrowClosed, color: "#9b2335", width: 16, height: 16 },
      style: { stroke: "#b48b83", strokeWidth: 1.5 }, labelStyle: { fill: "#64534c", fontSize: 11 },
      labelBgStyle: { fill: "#faf7f2", stroke: "#e9dfd1" }, labelBgPadding: [8, 5] as [number, number], labelBgBorderRadius: 5,
      data: { fullLabel: edge.label }
    }));
    return { nodes, edges };
  }, [graph]);

  return <section className="story-flow">
    <div className="story-flow-toolbar"><div className="story-flow-legend"><span><i />剧情</span><span><i className="ending" />结局</span></div><small>拖动画布浏览 · 滚轮缩放 · 点击连线查看完整选项</small></div>
    {graph.warnings?.length ? <p className="story-flow-warning">{graph.warnings.join("；")}</p> : null}
    <div className="story-flow-canvas">
      <ReactFlow key={nodes.map(node => node.id).join("|") + edges.map(edge => edge.id).join("|")} nodes={nodes} edges={edges} nodeTypes={nodeTypes}
        fitView fitViewOptions={{ padding: 0.15, maxZoom: 1 }} minZoom={0.12} maxZoom={1.8}
        nodesDraggable={false} nodesConnectable={false} edgesReconnectable={false} deleteKeyCode={null}
        onEdgeMouseEnter={(_, edge) => setOptionText(String(edge.data?.fullLabel || "场景跳转"))}
        onEdgeMouseLeave={() => setOptionText("")}
        onEdgeClick={(_, edge) => setOptionText(String(edge.data?.fullLabel || "场景跳转"))}
        onPaneClick={() => setOptionText("")}>
        <Background color="#ded5c9" gap={24} size={1} />
        <Controls showInteractive={false} position="bottom-right" />
      </ReactFlow>
      {optionText && <div className="story-flow-option" role="status">{optionText}</div>}
    </div>
  </section>;
}
