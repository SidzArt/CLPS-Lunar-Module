import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { AdminLayout } from "../../admin/AdminLayout";
import {
  activateCodeVersion,
  adminQueryKeys,
  createCodeVersion,
  diffCodeVersions,
  fetchCodeVersionDetail,
  fetchCodeVersions,
  fetchHardwareVariables,
  renderCodeVersionPreview,
  validateCodeVersionSyntax,
  type CodeVersionRenderOut,
  type CodeVersionSyntaxValidationOut,
  type HardwareVariableRefOut,
  type PlaceholderSpecIn,
} from "../../api/adminEndpoints";

type ControllerKey = "wifi_bridge" | "motion_uno" | "moon_led_s3";
type EditorView = "edit" | "syntax" | "diff";

const CPP_KEYWORDS = new Set([
  "void",
  "int",
  "float",
  "double",
  "bool",
  "char",
  "const",
  "constexpr",
  "unsigned",
  "long",
  "short",
  "struct",
  "enum",
  "class",
  "if",
  "else",
  "for",
  "while",
  "return",
  "switch",
  "case",
  "break",
  "true",
  "false",
  "nullptr",
  "static",
]);

function renderHighlightedLine(line: string): React.ReactNode {
  const trimmed = line.trimStart();
  if (trimmed.startsWith("//") || trimmed.startsWith("/*") || trimmed.startsWith("*")) {
    return <span className="cpp-tok-comment">{line}</span>;
  }
  if (trimmed.startsWith("#")) {
    return <span className="cpp-tok-preproc">{line}</span>;
  }
  // Safe pure-JSX tokenizer splitting placeholder tokens, strings, and C++ keywords (zero innerHTML)
  const parts = line.split(/(\{\{[A-Z0-9_]+\}\}|"[^"]*"|\b[a-zA-Z_][a-zA-Z0-9_]*\b)/g);
  return parts.map((part, idx) => {
    if (!part) return null;
    if (/^\{\{[A-Z0-9_]+\}\}$/.test(part)) {
      return (
        <span key={idx} className="cpp-tok-placeholder">
          {part}
        </span>
      );
    }
    if (part.startsWith('"') && part.endsWith('"')) {
      return (
        <span key={idx} className="cpp-tok-string">
          {part}
        </span>
      );
    }
    if (CPP_KEYWORDS.has(part)) {
      return (
        <span key={idx} className="cpp-tok-keyword">
          {part}
        </span>
      );
    }
    return <span key={idx}>{part}</span>;
  });
}

function SplitPaneFirmwareWorkbench({ initialVersionId }: { initialVersionId?: string }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const [controllerKey, setControllerKey] = useState<ControllerKey>("motion_uno");
  const [selectedId, setSelectedId] = useState<string>(initialVersionId ?? "");
  const [compareBaseId, setCompareBaseId] = useState<string>("");
  const [viewMode, setViewMode] = useState<EditorView>("edit");
  const selectedIdRef = useRef<string>(selectedId);
  selectedIdRef.current = selectedId;

  // Draft editing state
  const [versionLabel, setVersionLabel] = useState("v1.0.1-draft");
  const [boardTarget, setBoardTarget] = useState("arduino:avr:uno");
  const [notes, setNotes] = useState("");
  const [sourceCode, setSourceCode] = useState(
    "// Draft controller firmware template\nvoid setup() {\n}\n\nvoid loop() {\n}\n",
  );
  const [placeholders, setPlaceholders] = useState<PlaceholderSpecIn[]>([]);
  const [activateOnSave, setActivateOnSave] = useState(false);

  // In-file & variable reference filters
  const [codeSearch, setCodeSearch] = useState("");
  const [varSearch, setVarSearch] = useState("");
  const [varCategory, setVarCategory] = useState("");

  // Diagnostics output state
  const [validationResult, setValidationResult] = useState<CodeVersionSyntaxValidationOut | null>(
    null,
  );
  const [renderResult, setRenderResult] = useState<CodeVersionRenderOut | null>(null);
  const [notice, setNotice] = useState<{ kind: "cyan" | "warn" | "error"; text: string } | null>(
    null,
  );

  const versionsQuery = useQuery({
    queryKey: adminQueryKeys.codeVersions(controllerKey),
    queryFn: () => fetchCodeVersions(controllerKey),
  });

  const detailQuery = useQuery({
    queryKey: adminQueryKeys.codeVersionDetail(selectedId),
    queryFn: () => fetchCodeVersionDetail(selectedId),
    enabled: Boolean(selectedId),
  });

  const diffQuery = useQuery({
    queryKey: ["admin", "firmwareDiff", compareBaseId, selectedId],
    queryFn: () => diffCodeVersions(compareBaseId, selectedId),
    enabled: viewMode === "diff" && Boolean(compareBaseId) && Boolean(selectedId),
  });

  const variablesQuery = useQuery({
    queryKey: adminQueryKeys.hardwareVariables,
    queryFn: () => fetchHardwareVariables(),
  });

  useEffect(() => {
    const list = versionsQuery.data;
    if (!list || list.length === 0) return;
    if (!selectedId || (detailQuery.isError && !list.some((v) => v.code_version_id === selectedId))) {
      const preferred = list.find((v) => v.is_active) ?? list[0];
      setSelectedId(preferred.code_version_id);
      if (list.length > 1) {
        const alt = list.find((v) => v.code_version_id !== preferred.code_version_id);
        if (alt) setCompareBaseId(alt.code_version_id);
      }
    }
  }, [versionsQuery.data, selectedId, detailQuery.isError]);

  useEffect(() => {
    const det = detailQuery.data;
    if (!det) return;
    setControllerKey(det.controller_key as ControllerKey);
    setBoardTarget(det.board_target);
    setSourceCode(det.source_code);
    setNotes(det.notes ?? "");
    setPlaceholders(
      (det.placeholders ?? []).map((p, idx) => ({
        placeholder_key: String(p.placeholder_key ?? ""),
        description: String(p.description ?? "Template variable"),
        data_type: (p.data_type as PlaceholderSpecIn["data_type"]) ?? "string",
        unit: p.unit ? String(p.unit) : null,
        required: Boolean(p.required ?? true),
        default_value: p.default_value ?? null,
        injection_format:
          (p.injection_format as PlaceholderSpecIn["injection_format"]) ?? "cpp_literal",
        order_index: Number(p.order_index ?? idx),
      })),
    );
  }, [detailQuery.data]);

  const saveVersionMutation = useMutation({
    mutationFn: () =>
      createCodeVersion({
        controller_key: controllerKey,
        version_label: versionLabel.trim(),
        source_code: sourceCode,
        language: "cpp",
        board_target: boardTarget.trim(),
        notes: notes.trim() || null,
        placeholders,
        activate: activateOnSave,
      }),
    onSuccess: async (created) => {
      const previousId = selectedIdRef.current;
      queryClient.setQueryData(adminQueryKeys.codeVersionDetail(created.code_version_id), created);
      if (previousId && previousId !== created.code_version_id) {
        setCompareBaseId(previousId);
      }
      setSelectedId(created.code_version_id);
      navigate(`/admin/codex/firmware/${created.code_version_id}`, { replace: true });
      await queryClient.refetchQueries({ queryKey: adminQueryKeys.codeVersions(controllerKey) });
      setNotice({
        kind: "cyan",
        text: `Saved immutable firmware snapshot "${created.version_label}" (checksum ${created.checksum.slice(0, 12)}...).`,
      });
    },
    onError: (err) =>
      setNotice({
        kind: "error",
        text: err instanceof Error ? err.message : "Failed to save firmware version.",
      }),
  });

  const activateMutation = useMutation({
    mutationFn: () => activateCodeVersion(selectedId),
    onSuccess: (activated) => {
      queryClient.invalidateQueries({ queryKey: adminQueryKeys.codeVersions(controllerKey) });
      queryClient.invalidateQueries({ queryKey: adminQueryKeys.codeVersionDetail(selectedId) });
      setNotice({
        kind: "cyan",
        text: `Marked "${activated.version_label}" active in PostgreSQL (no physical flashing executed).`,
      });
    },
    onError: (err) =>
      setNotice({
        kind: "error",
        text: err instanceof Error ? err.message : "Activation failed.",
      }),
  });

  const validateMutation = useMutation({
    mutationFn: () => validateCodeVersionSyntax(selectedId),
    onSuccess: (res) => {
      setValidationResult(res);
      setNotice({
        kind: res.valid_static_checks ? "cyan" : "warn",
        text: res.valid_static_checks
          ? "Static C/C++ brace & placeholder validation passed cleanly."
          : "Static validation flagged syntax or placeholder issues.",
      });
    },
    onError: (err) =>
      setNotice({ kind: "error", text: err instanceof Error ? err.message : "Validation failed." }),
  });

  const renderPreviewMutation = useMutation({
    mutationFn: () => {
      const values: Record<string, unknown> = {};
      for (const spec of placeholders) {
        if (spec.default_value !== null && spec.default_value !== undefined) {
          values[spec.placeholder_key] = spec.default_value;
        }
      }
      return renderCodeVersionPreview(selectedId, { values });
    },
    onSuccess: (res) => setRenderResult(res),
    onError: (err) =>
      setNotice({ kind: "error", text: err instanceof Error ? err.message : "Render preview failed." }),
  });

  function handleInsertVariable(ref: HardwareVariableRefOut) {
    const token = `{{${ref.key}}}`;
    const el = textareaRef.current;
    if (el && viewMode === "edit") {
      const start = el.selectionStart ?? sourceCode.length;
      const end = el.selectionEnd ?? sourceCode.length;
      const updated = sourceCode.slice(0, start) + token + sourceCode.slice(end);
      setSourceCode(updated);
      setTimeout(() => {
        el.focus();
        el.setSelectionRange(start + token.length, start + token.length);
      }, 0);
    } else {
      setSourceCode((prev) => `${prev}\n${token}`);
      setViewMode("edit");
    }

    if (!placeholders.some((p) => p.placeholder_key === ref.key)) {
      const dtype =
        ref.data_type === "int" ||
        ref.data_type === "float" ||
        ref.data_type === "bool" ||
        ref.data_type === "string"
          ? ref.data_type
          : "string";
      const inj =
        ref.injection_format === "cpp_literal" ||
        ref.injection_format === "int_flag" ||
        ref.injection_format === "c_identifier" ||
        ref.injection_format === "c_string"
          ? ref.injection_format
          : "cpp_literal";
      setPlaceholders((prev) => [
        ...prev,
        {
          placeholder_key: ref.key,
          description: ref.description,
          data_type: dtype,
          unit: ref.unit ?? null,
          required: true,
          default_value: ref.current_value ?? null,
          injection_format: inj,
          order_index: prev.length,
        },
      ]);
    }
    setNotice({
      kind: "cyan",
      text: `Inserted ${token} and added to draft placeholder allow-list.`,
    });
  }

  const lines = sourceCode.split("\n");
  const normalizedSearch = codeSearch.trim().toLowerCase();
  const variables = variablesQuery.data ?? [];
  const categories = Array.from(new Set(variables.map((v) => v.category))).sort();
  const filteredVariables = variables.filter((v) => {
    if (varCategory && v.category !== varCategory) return false;
    if (!varSearch.trim()) return true;
    const q = varSearch.trim().toLowerCase();
    return (
      v.key.toLowerCase().includes(q) ||
      v.description.toLowerCase().includes(q) ||
      v.source_table.toLowerCase().includes(q)
    );
  });

  return (
    <div style={{ display: "grid", gap: "1rem" }}>
      <div className="notice-banner warn">
        <div>
          <strong>No Auto-Flash Safety Policy:</strong> Saving creates an immutable database snapshot;
          Activating only marks the database active revision. Physical firmware flashing remains{" "}
          <code>BLOCKED — HARDWARE TEAM REQUIRED</code> until toolchain &amp; bench verification.
        </div>
      </div>

      {notice && (
        <div className={`notice-banner ${notice.kind}`} role="status">
          <span>{notice.text}</span>
        </div>
      )}

      <section className="glass-panel-strong" style={{ padding: "1rem 1.15rem" }}>
        <div className="admin-toolbar">
          <select
            className="input"
            aria-label="Controller target"
            value={controllerKey}
            onChange={(e) => {
              const nextCtrl = e.target.value as ControllerKey;
              setControllerKey(nextCtrl);
              setSelectedId("");
              setCompareBaseId("");
              setBoardTarget(
                nextCtrl === "motion_uno"
                  ? "arduino:avr:uno"
                  : nextCtrl === "moon_led_s3"
                    ? "esp32:esp32:esp32s3"
                    : "esp32:esp32:esp32",
              );
            }}
            style={{ width: "auto", minWidth: "180px" }}
          >
            <option value="motion_uno">motion_uno (Arduino UNO)</option>
            <option value="moon_led_s3">moon_led_s3 (ESP32-S3)</option>
            <option value="wifi_bridge">wifi_bridge (ESP32 Bridge)</option>
          </select>

          <select
            className="input"
            aria-label="Firmware version"
            value={selectedId}
            onChange={(e) => {
              setSelectedId(e.target.value);
              if (e.target.value) {
                navigate(`/admin/codex/firmware/${e.target.value}`, { replace: true });
              }
            }}
            style={{ flex: "1 1 240px" }}
          >
            {(versionsQuery.data ?? []).length === 0 && (
              <option value="">-- Draft (unsaved revision) --</option>
            )}
            {(versionsQuery.data ?? []).map((v) => (
              <option key={v.code_version_id} value={v.code_version_id}>
                {v.version_label} {v.is_active ? "(ACTIVE)" : ""} · {v.board_target}
              </option>
            ))}
          </select>

          <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap" }}>
            <button
              type="button"
              className={`btn${viewMode === "edit" ? " btn-primary" : ""}`}
              onClick={() => setViewMode("edit")}
            >
              Edit Draft
            </button>
            <button
              type="button"
              className={`btn${viewMode === "syntax" ? " btn-primary" : ""}`}
              onClick={() => setViewMode("syntax")}
            >
              Syntax View
            </button>
            <button
              type="button"
              className={`btn${viewMode === "diff" ? " btn-primary" : ""}`}
              onClick={() => setViewMode("diff")}
            >
              Compare Diff
            </button>
          </div>
        </div>
      </section>

      <div className="firmware-split-pane">
        {/* LEFT PANE: Source Editor / Syntax / Diff */}
        <section className="glass-panel-strong firmware-editor-pane">
          <div className="admin-form-grid-3" style={{ marginBottom: "0.75rem" }}>
            <div>
              <label className="field-label" htmlFor="fw-new-label">
                New Snapshot Label
              </label>
              <input
                id="fw-new-label"
                className="input"
                value={versionLabel}
                onChange={(e) => setVersionLabel(e.target.value)}
              />
            </div>
            <div>
              <label className="field-label" htmlFor="fw-board">
                Board Target (FQBN)
              </label>
              <input
                id="fw-board"
                className="input"
                value={boardTarget}
                onChange={(e) => setBoardTarget(e.target.value)}
              />
            </div>
            <div>
              <label className="field-label" htmlFor="fw-find">
                In-File Find
              </label>
              <input
                id="fw-find"
                type="search"
                className="input"
                placeholder="Search symbol or token..."
                value={codeSearch}
                onChange={(e) => setCodeSearch(e.target.value)}
              />
            </div>
          </div>

          {viewMode === "edit" && (
            <div className="firmware-code-wrap">
              <div className="firmware-gutter" aria-hidden="true">
                {lines.map((_, i) => (
                  <div key={i}>{i + 1}</div>
                ))}
              </div>
              <textarea
                ref={textareaRef}
                aria-label="Controller C++ firmware source editor"
                className="firmware-textarea"
                spellCheck={false}
                value={sourceCode}
                onChange={(e) => setSourceCode(e.target.value)}
              />
            </div>
          )}

          {viewMode === "syntax" && (
            <div className="firmware-highlight-wrap" role="region" aria-label="Syntax view">
              {lines.map((ln, idx) => {
                const matched =
                  normalizedSearch.length > 0 && ln.toLowerCase().includes(normalizedSearch);
                return (
                  <div
                    key={idx}
                    className={`firmware-code-line${matched ? " firmware-line-match" : ""}`}
                  >
                    <span className="firmware-ln">{idx + 1}</span>
                    <code>{renderHighlightedLine(ln)}</code>
                  </div>
                );
              })}
            </div>
          )}

          {viewMode === "diff" && (
            <div style={{ display: "grid", gap: "0.65rem" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", flexWrap: "wrap" }}>
                <label className="field-label" htmlFor="fw-base" style={{ margin: 0 }}>
                  Compare against base revision:
                </label>
                <select
                  id="fw-base"
                  className="input"
                  value={compareBaseId}
                  onChange={(e) => setCompareBaseId(e.target.value)}
                  style={{ width: "auto", minWidth: "220px" }}
                >
                  <option value="">Select base version...</option>
                  {(versionsQuery.data ?? []).map((v) => (
                    <option key={v.code_version_id} value={v.code_version_id}>
                      {v.version_label}
                    </option>
                  ))}
                </select>
                {diffQuery.data && (
                  <span style={{ fontSize: "0.82rem", color: "var(--text-secondary)" }}>
                    +{diffQuery.data.added_lines} / -{diffQuery.data.removed_lines} lines
                  </span>
                )}
              </div>

              <div className="firmware-highlight-wrap">
                {!compareBaseId ? (
                  <div style={{ padding: "0.75rem", color: "var(--text-muted)" }}>
                    Choose a base firmware version above to inspect line and placeholder differences.
                  </div>
                ) : diffQuery.isLoading ? (
                  <div style={{ padding: "0.75rem" }}>Computing unified diff...</div>
                ) : (
                  (diffQuery.data?.unified_diff || "No source differences between revisions.")
                    .split("\n")
                    .map((line, idx) => {
                      const cls = line.startsWith("+")
                        ? "diff-add"
                        : line.startsWith("-")
                          ? "diff-del"
                          : line.startsWith("@@")
                            ? "diff-hunk"
                            : "";
                      return (
                        <div key={idx} className={`firmware-code-line ${cls}`}>
                          <span className="firmware-ln">{idx + 1}</span>
                          <code>{line}</code>
                        </div>
                      );
                    })
                )}
              </div>
            </div>
          )}

          {/* Placeholder Manifest */}
          <div style={{ marginTop: "0.9rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.45rem" }}>
              <strong style={{ fontSize: "0.9rem" }}>
                Placeholder Allow-List ({placeholders.length})
              </strong>
              <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                Strict escaping by type &amp; injection_format
              </span>
            </div>
            <div className="admin-table-wrap">
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>Key</th>
                    <th>Type</th>
                    <th>Format</th>
                    <th>Default / Test Value</th>
                    <th>Remove</th>
                  </tr>
                </thead>
                <tbody>
                  {placeholders.length === 0 ? (
                    <tr>
                      <td colSpan={5}>No placeholders declared in this draft.</td>
                    </tr>
                  ) : (
                    placeholders.map((p, idx) => (
                      <tr key={`${p.placeholder_key}-${idx}`}>
                        <td>
                          <code>{`{{${p.placeholder_key}}}`}</code>
                        </td>
                        <td>{p.data_type}</td>
                        <td>{p.injection_format}</td>
                        <td>
                          <input
                            className="input"
                            aria-label={`Default value for ${p.placeholder_key}`}
                            value={p.default_value === null || p.default_value === undefined ? "" : String(p.default_value)}
                            onChange={(e) => {
                              const val = e.target.value;
                              setPlaceholders((prev) =>
                                prev.map((item, i) =>
                                  i === idx ? { ...item, default_value: val || null } : item,
                                ),
                              );
                            }}
                          />
                        </td>
                        <td>
                          <button
                            type="button"
                            className="btn"
                            onClick={() =>
                              setPlaceholders((prev) => prev.filter((_, i) => i !== idx))
                            }
                          >
                            Remove
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div style={{ display: "grid", gap: "0.7rem", marginTop: "0.9rem" }}>
            <div>
              <label className="field-label" htmlFor="fw-notes">
                Release / Review Notes
              </label>
              <input
                id="fw-notes"
                className="input"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
              />
            </div>

            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                flexWrap: "wrap",
                gap: "0.6rem",
              }}
            >
              <label style={{ display: "flex", gap: "0.45rem", fontSize: "0.84rem" }}>
                <input
                  type="checkbox"
                  checked={activateOnSave}
                  onChange={(e) => setActivateOnSave(e.target.checked)}
                />
                Activate new snapshot in DB on save
              </label>
              <div style={{ display: "flex", gap: "0.45rem", flexWrap: "wrap" }}>
                <button
                  type="button"
                  className="btn"
                  disabled={!selectedId || validateMutation.isPending}
                  onClick={() => validateMutation.mutate()}
                >
                  Validate Syntax
                </button>
                <button
                  type="button"
                  className="btn"
                  disabled={!selectedId || renderPreviewMutation.isPending}
                  onClick={() => renderPreviewMutation.mutate()}
                >
                  Render Preview
                </button>
                <button
                  type="button"
                  className="btn btn-cyan"
                  disabled={!selectedId || activateMutation.isPending}
                  onClick={() => activateMutation.mutate()}
                >
                  Activate Version
                </button>
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={saveVersionMutation.isPending}
                  onClick={() => saveVersionMutation.mutate()}
                >
                  {saveVersionMutation.isPending ? "Saving..." : "Save Immutable Version"}
                </button>
              </div>
            </div>
          </div>

          {validationResult && (
            <div className="glass-panel" style={{ padding: "0.85rem", marginTop: "0.9rem" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <strong>Static &amp; Placeholder Validation</strong>
                <span className={`pill-badge ${validationResult.valid_static_checks ? "ok" : "danger"}`}>
                  {validationResult.valid_static_checks ? "PASSED" : "ISSUES FOUND"}
                </span>
              </div>
              <p style={{ margin: "0.35rem 0 0", fontSize: "0.82rem", color: "var(--text-secondary)" }}>
                Toolchain available: <code>{String(validationResult.toolchain_available)}</code> —{" "}
                {validationResult.toolchain_note}
              </p>
              {(validationResult.errors ?? []).length > 0 && (
                <ul style={{ margin: "0.45rem 0 0", color: "var(--accent-amber)", fontSize: "0.82rem" }}>
                  {(validationResult.errors ?? []).map((err, i) => (
                    <li key={i}>{err}</li>
                  ))}
                </ul>
              )}
              {(validationResult.warnings ?? []).length > 0 && (
                <ul style={{ margin: "0.45rem 0 0", color: "var(--text-secondary)", fontSize: "0.82rem" }}>
                  {(validationResult.warnings ?? []).map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {renderResult && (
            <div className="glass-panel" style={{ padding: "0.85rem", marginTop: "0.9rem" }}>
              <strong style={{ fontSize: "0.88rem" }}>
                Rendered Output Preview (SHA-256: {renderResult.rendered_checksum_sha256.slice(0, 16)}...)
              </strong>
              <pre className="admin-json-pre" style={{ marginTop: "0.5rem" }}>
                {renderResult.rendered_source}
              </pre>
            </div>
          )}
        </section>

        {/* RIGHT PANE: Live Backend Variable Reference */}
        <aside className="glass-panel-strong firmware-variables-pane" aria-label="Variable reference">
          <h2 style={{ margin: "0 0 0.25rem", fontSize: "1.08rem" }}>Live Variable Reference</h2>
          <p style={{ margin: "0 0 0.75rem", fontSize: "0.82rem", color: "var(--text-secondary)" }}>
            Served from PostgreSQL calibrations, LED maps, and device config. Click{" "}
            <strong>Insert</strong> to inject <code>{"{{KEY}}"}</code> at your cursor.
          </p>

          <div style={{ display: "grid", gap: "0.5rem", marginBottom: "0.75rem" }}>
            <input
              type="search"
              className="input"
              aria-label="Filter hardware variables"
              placeholder="Filter key or description..."
              value={varSearch}
              onChange={(e) => setVarSearch(e.target.value)}
            />
            <select
              className="input"
              aria-label="Filter variable category"
              value={varCategory}
              onChange={(e) => setVarCategory(e.target.value)}
            >
              <option value="">All Categories ({variables.length})</option>
              {categories.map((cat) => (
                <option key={cat} value={cat}>
                  {cat}
                </option>
              ))}
            </select>
          </div>

          <div className="firmware-variable-list">
            {filteredVariables.map((v) => (
              <article key={v.key} className="glass-panel firmware-var-card">
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "0.5rem" }}>
                  <div>
                    <code style={{ fontSize: "0.82rem" }}>{`{{${v.key}}}`}</code>
                    <div style={{ fontSize: "0.74rem", color: "var(--text-muted)" }}>
                      {v.category} · {v.data_type}
                      {v.unit ? ` (${v.unit})` : ""}
                    </div>
                  </div>
                  <button
                    type="button"
                    className="btn btn-cyan"
                    style={{ padding: "0.28rem 0.6rem", fontSize: "0.78rem" }}
                    onClick={() => handleInsertVariable(v)}
                  >
                    Insert
                  </button>
                </div>
                <p style={{ margin: "0.4rem 0 0.3rem", fontSize: "0.8rem", color: "var(--text-secondary)" }}>
                  {v.description}
                </p>
                <div style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>
                  Live value:{" "}
                  <code>
                    {v.current_value === null || v.current_value === undefined
                      ? "UNVERIFIED / NULL"
                      : String(v.current_value)}
                  </code>
                </div>
              </article>
            ))}
          </div>
        </aside>
      </div>
    </div>
  );
}

export function AdminFirmwareEditorPage() {
  const { versionId } = useParams<{ versionId?: string }>();
  return (
    <AdminLayout
      title="Split-Pane Firmware Editor"
      subtitle="Immutable controller templates, syntax & brace validation, diff inspection, and live variable injection."
      requiredRoles={["hardware_admin", "system_admin"]}
    >
      {() => <SplitPaneFirmwareWorkbench initialVersionId={versionId} />}
    </AdminLayout>
  );
}
