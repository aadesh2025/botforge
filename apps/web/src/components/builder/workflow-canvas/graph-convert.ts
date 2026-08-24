import type { Edge, Node } from "@xyflow/react";
import type { WorkflowGraph } from "@/lib/api/types";
import type { WorkflowNodeData } from "./workflow-node";

/** `WorkflowVersion.graph` (backend JSON) <-> React Flow's `{nodes, edges}` shape.
 *
 * Position and label live as top-level per-node fields (not nested in `config`) — the
 * backend's `validate_graph`/node handlers only ever read specific named `config` keys, so an
 * extra sibling field rides along inert, but keeping it OUT of `config` avoids any chance of
 * colliding with a real config key a node type reads.
 */
export function graphToFlow(graph: WorkflowGraph): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = (graph.nodes ?? []).map((n, i) => ({
    id: n.id,
    type: "workflowNode",
    position: n.position ?? { x: 120 + (i % 4) * 240, y: 80 + Math.floor(i / 4) * 150 },
    data: {
      nodeType: n.type,
      config: n.config ?? {},
      label: n.label,
    } satisfies WorkflowNodeData,
  }));
  const edges: Edge[] = (graph.edges ?? []).map((e, i) => ({
    id: `e${i}-${e.source}-${e.target}-${e.condition ?? "_"}`,
    source: e.source,
    target: e.target,
    sourceHandle: e.condition,
    label: e.condition,
    type: "smoothstep",
  }));
  return { nodes, edges };
}

export function flowToGraph(nodes: Node[], edges: Edge[]): WorkflowGraph {
  return {
    nodes: nodes.map((n) => {
      const data = n.data as WorkflowNodeData;
      return {
        id: n.id,
        type: data.nodeType,
        config: data.config ?? {},
        position: { x: Math.round(n.position.x), y: Math.round(n.position.y) },
        ...(data.label ? { label: data.label } : {}),
      };
    }),
    edges: edges.map((e) => ({
      source: e.source,
      target: e.target,
      ...(e.sourceHandle ? { condition: e.sourceHandle } : {}),
    })),
  };
}

let counter = 0;
export function newNodeId(type: string): string {
  counter += 1;
  return `${type}_${Date.now().toString(36)}${counter}`;
}
