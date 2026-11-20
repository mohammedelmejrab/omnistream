// Zoom and fit as buttons, so every pan and zoom has a non-drag alternative (WCAG 2.5.7).
export interface ZoomControlsProps {
  onZoomIn(): void;
  onZoomOut(): void;
  onFit(): void;
}

export function ZoomControls({ onZoomIn, onZoomOut, onFit }: ZoomControlsProps) {
  return (
    <div className="zoom-controls" role="group" aria-label="Graph zoom">
      <button type="button" className="icon-button" onClick={onZoomIn} aria-label="Zoom in">
        +
      </button>
      <button type="button" className="icon-button" onClick={onZoomOut} aria-label="Zoom out">
        −
      </button>
      <button type="button" className="text-button" onClick={onFit}>
        Fit
      </button>
    </div>
  );
}
