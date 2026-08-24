"use client";

import { api } from "./client";
import type {
  ApiWorkflow,
  ApiWorkflowRun,
  ApiWorkflowStep,
  ApiWorkflowVersion,
  WorkflowGraph,
} from "./types";

export function listWorkflows(agentId: string) {
  return api<ApiWorkflow[]>(`/v1/agents/${agentId}/workflows`, { orgScoped: true });
}

export function createWorkflow(agentId: string, name: string, description?: string) {
  return api<ApiWorkflow>(`/v1/agents/${agentId}/workflows`, {
    method: "POST",
    orgScoped: true,
    body: { name, description: description ?? null },
  });
}

export function getWorkflow(workflowId: string) {
  return api<ApiWorkflow>(`/v1/workflows/${workflowId}`, { orgScoped: true });
}

export function updateWorkflow(workflowId: string, patch: { name?: string; description?: string }) {
  return api<ApiWorkflow>(`/v1/workflows/${workflowId}`, { method: "PATCH", orgScoped: true, body: patch });
}

export function deleteWorkflow(workflowId: string) {
  return api<void>(`/v1/workflows/${workflowId}`, { method: "DELETE", orgScoped: true });
}

export function listWorkflowVersions(workflowId: string) {
  return api<ApiWorkflowVersion[]>(`/v1/workflows/${workflowId}/versions`, { orgScoped: true });
}

export function createWorkflowVersion(workflowId: string, graph: WorkflowGraph) {
  return api<ApiWorkflowVersion>(`/v1/workflows/${workflowId}/versions`, {
    method: "POST",
    orgScoped: true,
    body: { graph },
  });
}

export function publishWorkflowVersion(workflowId: string, version: number) {
  return api<ApiWorkflow>(`/v1/workflows/${workflowId}/versions/${version}/publish`, {
    method: "POST",
    orgScoped: true,
  });
}

export function runWorkflow(workflowId: string, variables?: Record<string, unknown>) {
  return api<ApiWorkflowRun>(`/v1/workflows/${workflowId}/run`, {
    method: "POST",
    orgScoped: true,
    body: { variables: variables ?? {} },
  });
}

/** Runs the workflow's LATEST version (draft or published) — the canvas's "Test run" button. */
export function testRunWorkflow(workflowId: string, variables?: Record<string, unknown>) {
  return api<ApiWorkflowRun>(`/v1/workflows/${workflowId}/test-run`, {
    method: "POST",
    orgScoped: true,
    body: { variables: variables ?? {} },
  });
}

export function getWorkflowRun(runId: string) {
  return api<ApiWorkflowRun>(`/v1/workflow-runs/${runId}`, { orgScoped: true });
}

export function resumeWorkflowRun(runId: string, decision: "approved" | "rejected") {
  return api<ApiWorkflowRun>(`/v1/workflow-runs/${runId}/resume`, {
    method: "POST",
    orgScoped: true,
    body: { decision },
  });
}

export function cancelWorkflowRun(runId: string) {
  return api<ApiWorkflowRun>(`/v1/workflow-runs/${runId}/cancel`, { method: "POST", orgScoped: true });
}

export function listWorkflowRunSteps(runId: string) {
  return api<ApiWorkflowStep[]>(`/v1/workflow-runs/${runId}/steps`, { orgScoped: true });
}
