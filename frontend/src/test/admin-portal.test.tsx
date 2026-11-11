import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { apiFetch } from "../api/client";
import { ThemeProvider } from "../app/ThemeContext";
import { renderPage } from "../entry-server";
import { AdminDashboardPage } from "../pages/admin/AdminDashboardPage";
import { AdminFirmwareEditorPage } from "../pages/admin/AdminFirmwareEditorPage";
import { AdminLoginPage } from "../pages/admin/AdminLoginPage";
import { AdminUsersPage } from "../pages/admin/AdminUsersPage";

function renderAdminUi(ui: ReactNode, initialEntry = "/admin") {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <MemoryRouter initialEntries={[initialEntry]}>{ui}</MemoryRouter>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

describe("Phase 7 Admin Portal & Security Controls", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    document.cookie = "clps_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/";
    if (typeof window !== "undefined" && typeof window.localStorage?.clear === "function") {
      window.localStorage.clear();
    }
    if (typeof window !== "undefined" && typeof window.sessionStorage?.clear === "function") {
      window.sessionStorage.clear();
    }
  });

  it("apiFetch automatically sends X-CSRF-Token from clps_csrf cookie on mutating requests", async () => {
    document.cookie = "clps_csrf=test_csrf_hmac_token_123; path=/";
    const fetchSpy = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) =>
        new Response(JSON.stringify({ ok: true }), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchSpy);

    await apiFetch("/api/v1/sites", { method: "GET" });
    await apiFetch("/api/v1/admin/sites", {
      method: "POST",
      body: JSON.stringify({ site_code: "X" }),
    });

    const getInit = fetchSpy.mock.calls[0]?.[1] as RequestInit | undefined;
    const postInit = fetchSpy.mock.calls[1]?.[1] as RequestInit | undefined;
    const getHeaders = new Headers(getInit?.headers);
    const postHeaders = new Headers(postInit?.headers);

    expect(getHeaders.get("X-CSRF-Token")).toBeNull();
    expect(postHeaders.get("X-CSRF-Token")).toBe("test_csrf_hmac_token_123");
    expect(postInit?.credentials).toBe("include");
  });

  it("AdminLoginPage surfaces lockout error and stores zero tokens in web storage", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request) => {
        const url = String(input);
        if (url.includes("/api/v1/auth/csrf")) {
          return new Response(JSON.stringify({ csrf_token: "csrf-init" }), { status: 200 });
        }
        if (url.includes("/api/v1/auth/me")) {
          return new Response(JSON.stringify({ detail: "Not authenticated" }), { status: 401 });
        }
        if (url.includes("/api/v1/auth/login")) {
          return new Response(
            JSON.stringify({ detail: "Administrator account temporarily locked." }),
            { status: 423 },
          );
        }
        return new Response(JSON.stringify({}), { status: 200 });
      }),
    );

    renderAdminUi(<AdminLoginPage />, "/admin/login");

    fireEvent.change(screen.getByLabelText(/Username/i), { target: { value: "locked_op" } });
    fireEvent.change(screen.getByLabelText(/Password/i), {
      target: { value: "WrongPassword!23" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Sign In/i }));

    await screen.findByText(/temporarily locked/i);
    if (typeof window.localStorage?.length === "number") {
      expect(window.localStorage.length).toBe(0);
    }
    if (typeof window.sessionStorage?.length === "number") {
      expect(window.sessionStorage.length).toBe(0);
    }
  });

  it("AdminDashboardPage enforces max 2 horizontal rows and RBAC-filtered navigation", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request) => {
        const url = String(input);
        if (url.includes("/api/v1/auth/me")) {
          return new Response(
            JSON.stringify({
              admin_id: "00000000-0000-0000-0000-000000000001",
              username: "editor_one",
              display_name: "Site Editor",
              is_active: true,
              password_must_rotate: false,
              roles: ["site_editor"],
            }),
            { status: 200 },
          );
        }
        if (url.includes("/api/v1/admin/overview")) {
          return new Response(
            JSON.stringify({
              username: "editor_one",
              display_name: "Site Editor",
              roles: ["site_editor"],
              sites_total: 10,
              sites_published: 8,
              sites_draft: 2,
              sites_verified: 0,
              sites_archived: 0,
              media_total: 14,
              imports_total: 3,
              imports_open: 1,
              simulations_total: 5,
              codex_controllers_online: null,
              codex_controllers_total: null,
              codex_transport_mode: null,
              active_firmware_versions_count: null,
              recent_audit_count_24h: null,
              degraded_components_count: null,
            }),
            { status: 200 },
          );
        }
        return new Response(JSON.stringify({}), { status: 200 });
      }),
    );

    const { container } = renderAdminUi(<AdminDashboardPage />, "/admin");

    await screen.findByText("8 / 10");
    const rows = container.querySelectorAll(".admin-dashboard-row");
    expect(rows.length).toBe(2);

    expect(screen.getByText(/Landing Sites & Metrics/i)).toBeTruthy();
    expect(screen.queryByText(/Users & Roles/i)).toBeNull();
    expect(screen.queryByText(/Audit & Health/i)).toBeNull();
  });

  it("AdminUsersPage shows 403 Forbidden UI gate for non-super_admin users", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request) => {
        const url = String(input);
        if (url.includes("/api/v1/auth/me")) {
          return new Response(
            JSON.stringify({
              admin_id: "00000000-0000-0000-0000-000000000002",
              username: "editor_user",
              is_active: true,
              password_must_rotate: false,
              roles: ["site_editor"],
            }),
            { status: 200 },
          );
        }
        return new Response(JSON.stringify({}), { status: 200 });
      }),
    );

    renderAdminUi(<AdminUsersPage />, "/admin/users");
    await screen.findByText(/403 Forbidden/i);
    expect(screen.getByText(/Insufficient Role Permissions/i)).toBeTruthy();
  });

  it("AdminFirmwareEditorPage supports split-pane variable insertion, syntax/diff view, and safety disclosure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request) => {
        const url = String(input);
        if (url.includes("/api/v1/auth/me")) {
          return new Response(
            JSON.stringify({
              admin_id: "00000000-0000-0000-0000-000000000003",
              username: "hw_op",
              is_active: true,
              password_must_rotate: false,
              roles: ["hardware_admin"],
            }),
            { status: 200 },
          );
        }
        if (url.includes("/api/v1/admin/hardware/variables")) {
          return new Response(
            JSON.stringify([
              {
                key: "AZIMUTH_MAX_RATE",
                category: "calibration",
                source_table: "motor_calibrations",
                description: "Bench-measured NEMA17 max step rate",
                data_type: "int",
                unit: "steps/s",
                current_value: null,
                injection_format: "cpp_literal",
                example_placeholder: "{{AZIMUTH_MAX_RATE}}",
              },
            ]),
            { status: 200 },
          );
        }
        if (url.includes("/api/v1/admin/hardware/code-versions/ver-1")) {
          return new Response(
            JSON.stringify({
              code_version_id: "ver-1",
              controller_key: "motion_uno",
              version_label: "v1.0.0-seed",
              language: "cpp",
              board_target: "arduino:avr:uno",
              checksum: "abcdef1234567890",
              is_active: true,
              source_code: "void setup() {\n  int rate = 100;\n}",
              placeholders: [],
              builds: [],
              created_at: "2026-11-11T00:00:00Z",
            }),
            { status: 200 },
          );
        }
        if (url.includes("/api/v1/admin/hardware/code-versions")) {
          return new Response(
            JSON.stringify([
              {
                code_version_id: "ver-1",
                controller_key: "motion_uno",
                version_label: "v1.0.0-seed",
                language: "cpp",
                board_target: "arduino:avr:uno",
                checksum: "abcdef1234567890",
                is_active: true,
                placeholders: [],
                created_at: "2026-11-11T00:00:00Z",
              },
            ]),
            { status: 200 },
          );
        }
        return new Response(JSON.stringify({}), { status: 200 });
      }),
    );

    renderAdminUi(
      <Routes>
        <Route path="/admin/codex/firmware" element={<AdminFirmwareEditorPage />} />
        <Route path="/admin/codex/firmware/:versionId" element={<AdminFirmwareEditorPage />} />
      </Routes>,
      "/admin/codex/firmware",
    );

    await screen.findByText(/No Auto-Flash Safety Policy/i);
    await screen.findByText("{{AZIMUTH_MAX_RATE}}");
    expect(screen.getByText(/UNVERIFIED \/ NULL/i)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /^Insert$/i }));
    await waitFor(() => {
      const editor = screen.getByLabelText(/Controller C\+\+ firmware source editor/i) as HTMLTextAreaElement;
      expect(editor.value).toContain("{{AZIMUTH_MAX_RATE}}");
    });

    fireEvent.click(screen.getByRole("button", { name: /Syntax View/i }));
    await screen.findByRole("region", { name: /Syntax view/i });
  });

  it("SSR renders admin login and dynamic admin routes with noindex,nofollow and status 200", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ items: [], total: 0 }), { status: 200 })),
    );

    for (const route of ["/admin/login", "/admin", "/admin/sites/1", "/admin/codex/firmware/v1"]) {
      const res = await renderPage({ url: route, backendOrigin: "http://127.0.0.1:8000" });
      expect(res.statusCode).toBe(200);
      expect(res.headHtml).toContain('name="robots" content="noindex,nofollow"');
    }

    const unknownAdmin = await renderPage({
      url: "/admin/nonexistent-module",
      backendOrigin: "http://127.0.0.1:8000",
    });
    expect(unknownAdmin.statusCode).toBe(404);
  });
});
