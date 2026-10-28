import { memo, useEffect, useState } from "react";
import QRCode from "qrcode";

/** QR code linking a phone to the citizen SOS page (/sos) of THIS host, for
 * the demo. Generated locally — the URL is never sent to a QR service. */
function SosQrCard() {
  const url = typeof window !== "undefined" ? `${window.location.origin}/sos` : "/sos";
  const [img, setImg] = useState("");
  useEffect(() => {
    let alive = true;
    QRCode.toDataURL(url, { margin: 1, width: 264 })
      .then((d) => alive && setImg(d))
      .catch(() => alive && setImg(""));
    return () => {
      alive = false;
    };
  }, [url]);
  const secure = typeof window === "undefined" || window.isSecureContext;
  return (
    <div className="panel">
      <div className="panel-head">
        <h3>📱 Citizen SOS from a phone</h3>
      </div>
      <div className="sos-qr-panel">
        {img ? <img src={img} alt={`QR code for ${url}`} /> : null}
        <div>
          <p>
            Scan to open <a href="/sos" target="_blank" rel="noreferrer">{url}</a>. The SOS joins this live run at
            &ldquo;queued&rdquo; and goes through the same pipeline.
          </p>
          {!secure ? (
            <p className="hint">
              This page is on plain http, so phones will block &ldquo;Share my location&rdquo; — the citizen places the
              pin by hand. Serve over HTTPS for GPS (see DEPLOYMENT.md).
            </p>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export default memo(SosQrCard);
