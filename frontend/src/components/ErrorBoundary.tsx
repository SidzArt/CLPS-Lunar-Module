import { Component, type ErrorInfo, type ReactNode } from "react";

interface ErrorBoundaryProps {
  children: ReactNode;
  fallbackTitle?: string;
  fallbackMessage?: string;
}

interface ErrorBoundaryState {
  hasError: boolean;
  errorMessage: string;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, errorMessage: "" };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return {
      hasError: true,
      errorMessage: error.message || "Unexpected rendering error.",
    };
  }

  componentDidCatch(_error: Error, _info: ErrorInfo): void {
    // Error captured in component state for accessible recovery UI
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="glass-panel notice-banner error" role="alert">
          <div>
            <strong>{this.props.fallbackTitle || "Display Unavailable"}</strong>
            <p style={{ margin: "0.25rem 0 0", color: "var(--text-secondary)" }}>
              {this.props.fallbackMessage || this.state.errorMessage}
            </p>
          </div>
          <button
            type="button"
            className="btn"
            onClick={() => this.setState({ hasError: false, errorMessage: "" })}
          >
            Retry
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

