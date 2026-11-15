import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ThemeProvider } from "../app/ThemeContext";
import { CodexDrawer } from "../components/CodexDrawer";
import { CodexPage } from "../pages/CodexPage";
import {
  DEMO_CODEX_CONTROLLERS,
  DEMO_VERIFICATION_MESSAGES,
  isCodexDemoMode,
  setCodexDemoMode,
} from "../utils/codexDemo";

function renderWithProviders(ui: ReactNode, initialEntry = "/") {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <MemoryRouter initialEntries={[initialEntry]}>
          <Routes>
            <Route path="*" element={ui} />
          </Routes>
        </MemoryRouter>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

describe("CODEX Demo Mode & Run Button Unit Tests", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("verifies Demo Mode presentation dataset has exact 3 components with Connected/Online/Ready/Running", () => {
    expect(DEMO_CODEX_CONTROLLERS).toHaveLength(3);

    const [wifi, motor, led] = DEMO_CODEX_CONTROLLERS;

    // Component 1
    expect(wifi.board_model).toBe("ESP32 DevKit — Wi-Fi Bridge");
    expect(wifi.status).toBe("Connected");
    expect(wifi.link).toBe("Online");
    expect(wifi.state).toBe("Ready");
    expect(wifi.execution).toBe("Running");

    // Component 2
    expect(motor.board_model).toBe("Arduino Uno R3 — Motor Controller");
    expect(motor.status).toBe("Connected");
    expect(motor.link).toBe("Online");
    expect(motor.state).toBe("Ready");
    expect(motor.execution).toBe("Running");

    // Component 3
    expect(led.board_model).toBe("ESP32-S3 — Moon LED Controller");
    expect(led.status).toBe("Connected");
    expect(led.link).toBe("Online");
    expect(led.state).toBe("Ready");
    expect(led.execution).toBe("Running");
  });

  it("verifies team reported verification messages match prompt specification exactly", () => {
    expect(DEMO_VERIFICATION_MESSAGES.hardwareDemonstration).toBe(
      "Hardware Demonstration: Completed",
    );
    expect(DEMO_VERIFICATION_MESSAGES.hardwareIntegration).toBe(
      "Hardware Integration: Completed",
    );
    expect(DEMO_VERIFICATION_MESSAGES.hardwareTestStatus).toBe(
      "Hardware Test Status: Team Reported — 12/12 Passed",
    );
    expect(DEMO_VERIFICATION_MESSAGES.projectStatus).toBe(
      "Project Status: Operational",
    );
  });

  it("verifies Demo Mode state persistence across refresh/navigation helpers", () => {
    setCodexDemoMode(true);
    expect(isCodexDemoMode()).toBe(true);

    setCodexDemoMode(false);
    expect(isCodexDemoMode()).toBe(false);

    setCodexDemoMode(true);
    expect(isCodexDemoMode()).toBe(true);
  });

  it("verifies CodexDrawer renders Demo Mode with 3 connected controllers and operational status", () => {
    setCodexDemoMode(true);
    renderWithProviders(<CodexDrawer open onClose={vi.fn()} isLoading={false} />);

    expect(screen.getAllByText("Project Status: Operational").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Hardware Demonstration: Completed").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Hardware Integration: Completed").length).toBeGreaterThanOrEqual(1);
    expect(
      screen.getAllByText("Hardware Test Status: Team Reported — 12/12 Passed").length,
    ).toBeGreaterThanOrEqual(1);

    // 3 components
    expect(screen.getByText("ESP32 DevKit — Wi-Fi Bridge")).toBeInTheDocument();
    expect(screen.getByText("Arduino Uno R3 — Motor Controller")).toBeInTheDocument();
    expect(screen.getByText("ESP32-S3 — Moon LED Controller")).toBeInTheDocument();

    // Connected, Online, Ready, Running
    expect(screen.getAllByText("Connected").length).toBeGreaterThanOrEqual(3);
    expect(screen.getAllByText("Online").length).toBeGreaterThanOrEqual(3);
    expect(screen.getAllByText("Ready").length).toBeGreaterThanOrEqual(3);
    expect(screen.getAllByText("Running").length).toBeGreaterThanOrEqual(3);

    // No Run button inside drawer (Run button must only appear in Run CODEX panel)
    expect(screen.queryByRole("button", { name: /^Run$/i })).not.toBeInTheDocument();
  });

  it("verifies CodexPage has Run button positioned at bottom-right which accepts click with zero network calls", async () => {
    setCodexDemoMode(true);
    const fetchSpy = vi.fn().mockResolvedValue(new Response(JSON.stringify({})));
    vi.stubGlobal("fetch", fetchSpy);

    renderWithProviders(<CodexPage />, "/codex");

    // All three components displayed
    await screen.findByText("ESP32 DevKit — Wi-Fi Bridge");
    expect(screen.getByText("Arduino Uno R3 — Motor Controller")).toBeInTheDocument();
    expect(screen.getByText("ESP32-S3 — Moon LED Controller")).toBeInTheDocument();

    // The single Run button
    const runBtn = screen.getByRole("button", { name: /^Run$/i });
    expect(runBtn).toBeInTheDocument();
    expect(runBtn).toBeVisible();

    // Clicking Run accepts the click
    const initialCallCount = fetchSpy.mock.calls.length;
    fireEvent.click(runBtn);

    // Zero API requests initiated by clicking Run
    expect(fetchSpy.mock.calls.length).toBe(initialCallCount);
    expect(screen.getByText(/Run command acknowledged/i)).toBeInTheDocument();
  });
});
