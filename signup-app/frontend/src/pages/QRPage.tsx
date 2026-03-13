import { QRCodeSVG } from 'qrcode.react'

export default function QRPage() {
  const signupUrl = window.location.origin

  return (
    <div className="qr-page">
      <div className="qr-container">
        <div className="qr-logo" aria-hidden="true">🤖</div>
        <h1 className="qr-title">AnythingLLM Demo</h1>
        <p className="qr-subtitle">Scan to sign up for your personal AI workspace</p>

        <div className="qr-code-wrap">
          <QRCodeSVG
            value={signupUrl}
            size={280}
            bgColor="#ffffff"
            fgColor="#0d1117"
            level="M"
            marginSize={2}
          />
        </div>

        <p className="qr-url">{signupUrl}</p>
      </div>
    </div>
  )
}
