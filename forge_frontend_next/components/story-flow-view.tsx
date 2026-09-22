"use client";

import { useEffect, useMemo, useState } from "react";
import { ReactFlow, Background, Controls, Handle, MiniMap, Position, MarkerType, useNodesState, type ReactFlowInstance, type NodeProps, type Node, type Edge } from "@xyflow/react";
import { compactStoryPositions, nearestCardHandles, primaryRouteEdgeIds, readingNodeIds, returnEdgeIds, type StoryGraph } from "./story-graph-data";

type StoryNode = Node<{
  label: string;
  kind: string;
  order: number;
  internalContinuationCount: number;
  internalLoopCount: number;
  internalLoopLabels: string[];
  focusRole: "" | "current" | "incoming" | "outgoing" | "both";
}, "story">;
function StoryCard({ data }: NodeProps<StoryNode>) {
  const focusLabel = data.focusRole === "current" ? "当前" : data.focusRole === "incoming" ? "来源" : data.focusRole === "outgoing" ? "去向" : data.focusRole === "both" ? "往返" : "";
  return <div className={`story-flow-card ${data.kind}${data.internalLoopCount ? " has-loop" : ""}${data.focusRole ? ` focus-${data.focusRole}` : ""}`} title={data.label}>
    <Handle id="target-left" type="target" position={Position.Left} />
    <Handle id="target-right" type="target" position={Position.Right} />
    <Handle id="target-top" type="target" position={Position.Top} />
    <Handle id="target-bottom" type="target" position={Position.Bottom} />
    <span className="story-flow-card-meta"><span>{data.kind === "start" ? "故事起点" : data.kind === "ending" ? "故事结局" : data.kind === "missing" ? "目标缺失" : "剧情场景"}{focusLabel && <b className={`story-flow-focus-role ${data.focusRole}`}>{focusLabel}</b>}</span><i>{String(data.order).padStart(2, "0")}</i></span>
    <strong>{data.label}</strong>
    {(data.internalContinuationCount > 0 || data.internalLoopCount > 0) && <span className="story-flow-card-flags">
      {data.internalContinuationCount > 0 && <i className="continuation">场景内继续 ×{data.internalContinuationCount}</i>}
      {data.internalLoopCount > 0 && <i className="loop" title={`循环选项：${data.internalLoopLabels.join("、")}`}>内部循环 ×{data.internalLoopCount}</i>}
    </span>}
    <Handle id="source-left" type="source" position={Position.Left} />
    <Handle id="source-right" type="source" position={Position.Right} />
    <Handle id="source-top" type="source" position={Position.Top} />
    <Handle id="source-bottom" type="source" position={Position.Bottom} />
  </div>;
}
const nodeTypes = { story: StoryCard };

export function StoryFlowView({ graph, viewportVersion = 0, fullscreen = false, onToggleFullscreen }: {
  graph: StoryGraph;
  viewportVersion?: number;
  fullscreen?: boolean;
  onToggleFullscreen?: () => void;
}) {
  const [optionText, setOptionText] = useState("");
  const [activeNodeId, setActiveNodeId] = useState<string | null>(null);
  const [activeEdgeId, setActiveEdgeId] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<"reading" | "overview">("overview");
  const [flow, setFlow] = useState<ReactFlowInstance<StoryNode, Edge> | null>(null);
  const layoutResult = useMemo(() => {
    const returnIds = returnEdgeIds(graph);
    const primaryIds = primaryRouteEdgeIds(graph, returnIds);
    const positions = compactStoryPositions(graph, returnIds);
    const nodes: StoryNode[] = graph.nodes.map(node => {
      const point = positions.get(node.id) || { x: 0, y: 0, order: 1 };
      return {
        id: node.id,
        type: "story",
        position: { x: point.x, y: point.y },
        data: {
          label: node.label,
          kind: node.kind,
          order: point.order,
          internalContinuationCount: node.internalContinuationCount || 0,
          internalLoopCount: node.internalLoopCount || 0,
          internalLoopLabels: node.internalLoopLabels || [],
          focusRole: ""
        }
      };
    });
    const nodeLabels = new Map(graph.nodes.map(node => [node.id, node.label]));
    const edges: Edge[] = graph.edges.map(edge => {
      const isReturn = returnIds.has(edge.id);
      const isPrimary = primaryIds.has(edge.id);
      const shortOption = edge.label ? (edge.label.length > 10 ? `${edge.label.slice(0, 10)}…` : edge.label) : "";
      const returnLabel = `↶ 回到${nodeLabels.get(edge.target) || edge.target}${shortOption ? ` · ${shortOption}` : ""}`;
      return {
        ...edge,
        ...nearestCardHandles(positions.get(edge.source) || { x: 0, y: 0 }, positions.get(edge.target) || { x: 0, y: 0 }),
        type: isReturn ? "bezier" : "smoothstep",
        className: isReturn ? "story-flow-edge-return" : isPrimary ? "story-flow-edge-primary" : "story-flow-edge-secondary",
        label: undefined,
        interactionWidth: 24,
        markerEnd: { type: MarkerType.ArrowClosed, color: isReturn ? "#84283a" : isPrimary ? "#9b2335" : "#bba9a1", width: 16, height: 16 },
        style: isReturn
          ? { stroke: "#84283a", strokeWidth: 2.1, strokeDasharray: "7 5", opacity: .58 }
          : isPrimary
            ? { stroke: "#aa8179", strokeWidth: 1.6, opacity: .76 }
            : { stroke: "#c8b9b0", strokeWidth: 1.15, strokeDasharray: "3 6", opacity: .18 },
        labelStyle: { fill: isReturn ? "#84283a" : "#64534c", fontSize: 11, fontWeight: isReturn ? 700 : 400 },
        labelBgStyle: { fill: isReturn ? "#fff4f2" : "#faf7f2", stroke: isReturn ? "#d9a8a5" : "#e9dfd1" },
        labelBgPadding: [8, 5] as [number, number],
        labelBgBorderRadius: 5,
        data: {
          isReturn,
          isPrimary,
          displayLabel: isReturn ? returnLabel : shortOption,
          fullLabel: isReturn
            ? `循环路径：${nodeLabels.get(edge.source) || edge.source} → ${nodeLabels.get(edge.target) || edge.target}${edge.label ? `（选项：${edge.label}）` : ""}`
            : edge.label
        }
      };
    });
    return {
      nodes,
      edges,
      returnCount: returnIds.size,
      internalLoopCount: graph.nodes.reduce((sum, node) => sum + (node.internalLoopCount || 0), 0)
    };
  }, [graph]);
  const [nodes, setNodes, onNodesChange] = useNodesState<StoryNode>(layoutResult.nodes);
  const { edges, returnCount, internalLoopCount } = layoutResult;
  useEffect(() => setNodes(layoutResult.nodes), [layoutResult.nodes, setNodes]);
  useEffect(() => {
    if (!flow) return;
    const frame = requestAnimationFrame(() => void flow.fitView({ padding: 0.13, maxZoom: 1, duration: 320 }));
    return () => cancelAnimationFrame(frame);
  }, [flow, viewportVersion]);
  const focusContext = useMemo(() => {
    if (!activeNodeId) return null;
    const incoming = graph.edges.filter(edge => edge.target === activeNodeId);
    const outgoing = graph.edges.filter(edge => edge.source === activeNodeId);
    const incomingIds = new Set(incoming.map(edge => edge.source));
    const outgoingIds = new Set(outgoing.map(edge => edge.target));
    return {
      incomingIds,
      outgoingIds,
      reciprocalIds: new Set([...incomingIds].filter(id => outgoingIds.has(id)))
    };
  }, [activeNodeId, graph]);
  const displayNodes = useMemo(() => nodes.map(node => {
    const isCurrent = node.id === activeNodeId;
    const isIncoming = Boolean(focusContext?.incomingIds.has(node.id));
    const isOutgoing = Boolean(focusContext?.outgoingIds.has(node.id));
    const focusRole: StoryNode["data"]["focusRole"] = isCurrent ? "current" : isIncoming && isOutgoing ? "both" : isOutgoing ? "outgoing" : "";
    return {
      ...node,
      data: { ...node.data, focusRole },
      hidden: Boolean(focusContext && !focusRole),
      style: { ...node.style, opacity: 1, transition: "opacity 160ms ease" }
    };
  }), [activeNodeId, focusContext, nodes]);
  const displayEdges = useMemo(() => {
    const livePositions = new Map(nodes.map(node => [node.id, node.position]));
    return edges.map(edge => {
      const connected = activeNodeId ? edge.source === activeNodeId : false;
      const direction = connected && focusContext?.reciprocalIds.has(edge.target) ? "both" : connected ? "outgoing" : "";
      const hovered = edge.id === activeEdgeId;
      const focused = connected || hovered;
      const defaultOpacity = edge.data?.isReturn ? .58 : edge.data?.isPrimary ? .76 : .18;
      const opacity = activeNodeId ? (connected ? 1 : 0) : hovered ? 1 : defaultOpacity;
      const focusColor = direction === "both" ? "#8f4054" : "#9b2335";
      const markerColor = focused
        ? focusColor
        : activeNodeId ? "#e5ddd7"
          : edge.data?.isReturn ? "#a66672" : edge.data?.isPrimary ? "#b28b84" : "#ded4ce";
      return {
        ...edge,
        hidden: Boolean(activeNodeId && !connected),
        ...nearestCardHandles(livePositions.get(edge.source) || { x: 0, y: 0 }, livePositions.get(edge.target) || { x: 0, y: 0 }),
        type: connected ? "smoothstep" : edge.type,
        label: connected ? direction === "both" ? "可往返" : "前往下一场景" : hovered && edge.data?.displayLabel ? String(edge.data.displayLabel) : undefined,
        style: { ...edge.style, opacity, stroke: connected ? focusColor : edge.style?.stroke, strokeDasharray: connected ? undefined : edge.style?.strokeDasharray, strokeWidth: focused ? 2.35 : edge.style?.strokeWidth },
        labelStyle: connected ? { fill: focusColor, fontSize: 11, fontWeight: 700 } : edge.labelStyle,
        labelBgStyle: connected ? { fill: "#fffdf9", stroke: "#deb8be" } : edge.labelBgStyle,
        markerStart: direction === "both" ? { type: MarkerType.ArrowClosed, color: focusColor, width: 16, height: 16 } : undefined,
        markerEnd: { type: MarkerType.ArrowClosed, color: markerColor, width: 16, height: 16 },
        zIndex: focused ? 10 : 0
      };
    });
  }, [activeEdgeId, activeNodeId, edges, focusContext, nodes]);

  const focusReading = () => {
    setActiveNodeId(null);
    setActiveEdgeId(null);
    setViewMode("reading");
    void flow?.fitView({ nodes: readingNodeIds(graph).map(id => ({ id })), padding: 0.22, minZoom: 0.72, maxZoom: 1, duration: 320 });
  };
  const showOverview = () => {
    setActiveNodeId(null);
    setActiveEdgeId(null);
    setViewMode("overview");
    setOptionText("");
    void flow?.fitView({ padding: 0.16, maxZoom: 0.86, duration: 360 });
  };
  const resetLayout = () => {
    setActiveNodeId(null);
    setActiveEdgeId(null);
    setNodes(layoutResult.nodes);
    setViewMode("overview");
    setOptionText("已恢复自动排列");
    requestAnimationFrame(() => void flow?.fitView({ padding: 0.16, maxZoom: 0.86, duration: 360 }));
  };

  return <section className="story-flow">
    <div className="story-flow-toolbar">
      <div className="story-flow-view-switch" aria-label="流程图查看方式">
        <button type="button" className={viewMode === "reading" ? "active" : ""} onClick={focusReading}>聚焦阅读</button>
        <button type="button" className={viewMode === "overview" ? "active" : ""} onClick={showOverview}>全图总览</button>
        <button type="button" onClick={resetLayout}>恢复排列</button>
      </div>
      <div className="story-flow-legend"><span><i className="route" />主干</span><span><i className="secondary" />其他跳转</span><span><i className="ending" />结局</span><span><i className="return" />循环</span></div>
      <small>连线自动吸附四个方向 · 点击场景查看相关路线</small>
    </div>
    {(returnCount > 0 || internalLoopCount > 0) && <p className="story-flow-cycle-summary">
      本流程包含{returnCount > 0 ? ` ${returnCount} 条跨场景循环` : ""}{returnCount > 0 && internalLoopCount > 0 ? "，以及" : ""}{internalLoopCount > 0 ? ` ${internalLoopCount} 处场景内循环` : ""}；循环并非遗漏，已在图中单独标出。
    </p>}
    {graph.warnings?.length ? <p className="story-flow-warning">{graph.warnings.join("；")}</p> : null}
    <div className="story-flow-canvas">
      <ReactFlow key={nodes.map(node => node.id).join("|") + edges.map(edge => edge.id).join("|")} nodes={displayNodes} edges={displayEdges} nodeTypes={nodeTypes}
        fitView fitViewOptions={{ padding: 0.13, maxZoom: 1 }} minZoom={0.12} maxZoom={1.8}
        onInit={setFlow}
        onNodesChange={onNodesChange}
        nodesDraggable nodesConnectable={false} edgesReconnectable={false} deleteKeyCode={null}
        onNodeClick={(_, node) => {
          setViewMode("reading");
          setActiveNodeId(node.id);
          setActiveEdgeId(null);
          setOptionText("");
          const outgoingIds = graph.edges.filter(edge => edge.source === node.id).map(edge => edge.target);
          void flow?.fitView({ nodes: [node.id, ...new Set(outgoingIds)].map(id => ({ id })), padding: 0.28, minZoom: 0.78, maxZoom: 1.08, duration: 300 });
        }}
        onEdgeMouseEnter={(_, edge) => { setActiveEdgeId(edge.id); setOptionText(String(edge.data?.fullLabel || "直接进入下一场景")); }}
        onEdgeMouseLeave={() => { setActiveEdgeId(null); setOptionText(""); }}
        onEdgeClick={(_, edge) => { setActiveEdgeId(edge.id); setOptionText(String(edge.data?.fullLabel || "直接进入下一场景")); }}
        onPaneClick={() => { setActiveNodeId(null); setActiveEdgeId(null); setOptionText(""); }}>
        <Background color="#ded5c9" gap={24} size={1} />
        <MiniMap position="bottom-left" pannable zoomable ariaLabel="剧情流程缩略图"
          nodeColor={node => node.data?.kind === "ending" ? "#b85c67" : node.data?.kind === "start" ? "#9b2335" : "#cbbbae"} />
        <Controls
          showInteractive={false}
          showFitView={!onToggleFullscreen}
          position="bottom-right"
          fitViewOptions={{ padding: 0.16, duration: 300 }}
          onFitView={() => setViewMode("overview")}
        >
          {onToggleFullscreen && <button
            className="react-flow__controls-button story-flow-fullscreen-control"
            type="button"
            aria-label={fullscreen ? "退出全屏" : "全屏查看流程图"}
            aria-pressed={fullscreen}
            title={fullscreen ? "退出全屏" : "全屏查看"}
            onClick={onToggleFullscreen}
          >
            {fullscreen ? (
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5" /></svg>
            ) : (
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 4H4v5M15 4h5v5M9 20H4v-5M15 20h5v-5" /></svg>
            )}
          </button>}
        </Controls>
      </ReactFlow>
      {optionText && <div className="story-flow-option" role="status">{optionText}</div>}
    </div>
  </section>;
}
