import { beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NewAgentDialog } from "./new-agent-dialog";
import { useSession } from "@/lib/store/session";

const listAgentTemplates = vi.fn();
vi.mock("@/lib/api/agents", () => ({ listAgentTemplates: () => listAgentTemplates() }));

const TEMPLATES = [
  {
    id: "customer_support",
    label: "Customer Support",
    icon: "LifeBuoy",
    description: "Resolves issues and answers customer questions.",
    system_prompt: "You are a customer-support agent.",
    welcome_message: "Hi!",
    suggested_prompts: ["How do I get started?"],
    tone: "Friendly",
    suggested_next_step: "Attach a knowledge base.",
  },
  {
    id: "appointment_scheduler",
    label: "Appointment Scheduler",
    // An icon the frontend doesn't ship, to prove the picker falls back instead of crashing.
    icon: "NotARealIcon",
    description: "Books, reschedules, and manages appointments.",
    system_prompt: "You are a scheduling assistant.",
    welcome_message: "Hi!",
    suggested_prompts: [],
    tone: "Concise",
    suggested_next_step: "Connect a calendar.",
  },
];

function renderDialog(onSubmit = vi.fn().mockResolvedValue(undefined)) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <NewAgentDialog open onOpenChange={vi.fn()} onSubmit={onSubmit} />
    </QueryClientProvider>,
  );
  return onSubmit;
}

beforeEach(() => {
  vi.clearAllMocks();
  useSession.setState({ activeOrgId: "org-1" });
  listAgentTemplates.mockResolvedValue(TEMPLATES);
});

describe("NewAgentDialog", () => {
  it("offers every template plus a start-from-scratch escape hatch", async () => {
    renderDialog();
    expect(await screen.findByText("Customer Support")).toBeInTheDocument();
    expect(screen.getByText("Appointment Scheduler")).toBeInTheDocument();
    expect(screen.getByText("Start from scratch")).toBeInTheDocument();
  });

  it("creates from the picked template, pre-filling the name with its label", async () => {
    const onSubmit = renderDialog();
    fireEvent.click(await screen.findByText("Customer Support"));

    const name = screen.getByLabelText("Agent name") as HTMLInputElement;
    expect(name.value).toBe("Customer Support");

    fireEvent.click(screen.getByRole("button", { name: /create & configure/i }));
    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith({ name: "Customer Support", templateId: "customer_support" }),
    );
  });

  it("sends templateId null for start-from-scratch — today's blank agent is unchanged", async () => {
    const onSubmit = renderDialog();
    fireEvent.click(await screen.findByText("Start from scratch"));

    const name = screen.getByLabelText("Agent name") as HTMLInputElement;
    expect(name.value).toBe(""); // a blank agent gets no suggested name

    fireEvent.change(name, { target: { value: "My Bot" } });
    fireEvent.click(screen.getByRole("button", { name: /create & configure/i }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith({ name: "My Bot", templateId: null }));
  });

  it("lets you go back and change your mind about the template", async () => {
    const onSubmit = renderDialog();
    fireEvent.click(await screen.findByText("Customer Support"));
    fireEvent.click(screen.getByRole("button", { name: /back/i }));
    fireEvent.click(screen.getByText("Appointment Scheduler"));

    fireEvent.click(screen.getByRole("button", { name: /create & configure/i }));
    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith({
        name: "Appointment Scheduler",
        templateId: "appointment_scheduler",
      }),
    );
  });

  it("keeps the typed name when the create fails, instead of dropping the dialog", async () => {
    const onSubmit = vi.fn().mockRejectedValue(new Error("Agent limit reached."));
    renderDialog(onSubmit);
    fireEvent.click(await screen.findByText("Customer Support"));
    fireEvent.click(screen.getByRole("button", { name: /create & configure/i }));

    expect(await screen.findByText("Agent limit reached.")).toBeInTheDocument();
    expect((screen.getByLabelText("Agent name") as HTMLInputElement).value).toBe("Customer Support");
  });

  it("won't submit an empty name", async () => {
    renderDialog();
    fireEvent.click(await screen.findByText("Start from scratch"));
    expect(screen.getByRole("button", { name: /create & configure/i })).toBeDisabled();
  });
});
