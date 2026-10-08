import { Component } from "react";

/** Catches a render/lifecycle error in its subtree so one broken section never
 * blanks the whole page. The error and React's component stack are logged to
 * the console; the section shows what failed and a Retry that remounts it. */
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
    this.reset = this.reset.bind(this);
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error(`[AquaSentinel] "${this.props.name || "section"}" crashed while rendering:`, error, info?.componentStack || "");
  }

  reset() {
    this.setState({ error: null });
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    return (
      <div className="panel output-step-error" role="alert">
        <div className="panel-head">
          <h3>{this.props.name || "This section"}</h3>
          <span className="badge crit">RUNTIME ERROR</span>
        </div>
        <p className="error-text">{String(error?.message || error)}</p>
        <p className="hint">The rest of the page still works. Details are in the browser console (F12).</p>
        <button type="button" className="primary" onClick={this.reset}>
          Retry this section
        </button>
      </div>
    );
  }
}
