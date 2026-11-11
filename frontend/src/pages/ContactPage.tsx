import { useMutation } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { submitContactForm, type ContactSubmitOut } from "../api/endpoints";
import { SiteHeader } from "../components/SiteHeader";
import { UtilitiesFooter } from "../components/UtilitiesFooter";
import { HeadTags } from "../seo/HeadTags";

export function ContactPage() {
  const [senderName, setSenderName] = useState("");
  const [senderEmail, setSenderEmail] = useState("");
  const [subject, setSubject] = useState("");
  const [messageBody, setMessageBody] = useState("");
  const [websiteHoneypot, setWebsiteHoneypot] = useState("");
  const [receipt, setReceipt] = useState<ContactSubmitOut | null>(null);

  const contactMutation = useMutation({
    mutationFn: (payload: Parameters<typeof submitContactForm>[0]) =>
      submitContactForm(payload),
    onSuccess: (res) => {
      setReceipt(res);
    },
  });

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    contactMutation.mutate({
      sender_name: senderName.trim(),
      sender_email: senderEmail.trim(),
      subject: subject.trim(),
      message_body: messageBody.trim(),
      website: websiteHoneypot,
    });
  }

  return (
    <div className="page-shell">
      <HeadTags
        meta={{
          title: "Contact Support — CLPS Luna Browser",
          description:
            "Submit scientific dataset feedback, landing-site questions, or technical bug reports to the CLPS Luna Browser team.",
          canonicalPath: "/contact",
          robots: "index,follow",
          ogType: "website",
          breadcrumbs: [
            { name: "Home", path: "/" },
            { name: "Contact", path: "/contact" },
          ],
        }}
      />

      <SiteHeader
        subtitle="Support & Assist"
        rightActions={
          <Link to="/" className="btn">
            &lt;- Home
          </Link>
        }
      />

      <main id="main-content" className="page-content-layer container" style={{ maxWidth: "700px" }}>
        <section className="glass-panel-strong" style={{ padding: "1.5rem" }}>
          <h1 style={{ margin: "0 0 0.45rem", fontSize: "1.6rem" }}>Contact Support</h1>
          <p style={{ margin: "0 0 1.2rem", color: "var(--text-secondary)", fontSize: "0.92rem" }}>
            Report landing-site provenance corrections, simulation issues, or UI accessibility
            bugs. Messages are recorded securely via `POST /api/v1/contact`.
          </p>

          {receipt ? (
            <div className="notice-banner cyan" role="status">
              <div>
                <strong style={{ display: "block", marginBottom: "0.25rem" }}>
                  Message Received ({receipt.status})
                </strong>
                <div style={{ fontSize: "0.86rem", color: "var(--text-secondary)" }}>
                  Reference ID: <code className="mono">{receipt.message_id}</code>
                </div>
                <p style={{ margin: "0.35rem 0 0", fontSize: "0.86rem" }}>
                  {receipt.notice}
                </p>
              </div>
            </div>
          ) : (
            <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "0.9rem" }}>
              {/* Hidden spam honeypot field matched to backend ContactSubmitIn.website */}
              <div style={{ position: "absolute", left: "-9999px" }} aria-hidden="true">
                <label htmlFor="contact-website-trap">Leave blank</label>
                <input
                  id="contact-website-trap"
                  type="text"
                  tabIndex={-1}
                  autoComplete="off"
                  value={websiteHoneypot}
                  onChange={(event) => setWebsiteHoneypot(event.target.value)}
                />
              </div>

              <div className="responsive-grid-2">
                <div>
                  <label htmlFor="contact-name" className="field-label">
                    Your Name
                  </label>
                  <input
                    id="contact-name"
                    type="text"
                    className="input"
                    value={senderName}
                    onChange={(event) => setSenderName(event.target.value)}
                    minLength={2}
                    required
                  />
                </div>
                <div>
                  <label htmlFor="contact-email" className="field-label">
                    Email Address
                  </label>
                  <input
                    id="contact-email"
                    type="email"
                    className="input"
                    value={senderEmail}
                    onChange={(event) => setSenderEmail(event.target.value)}
                    required
                  />
                </div>
              </div>

              <div>
                <label htmlFor="contact-subject" className="field-label">
                  Subject
                </label>
                <input
                  id="contact-subject"
                  type="text"
                  className="input"
                  value={subject}
                  onChange={(event) => setSubject(event.target.value)}
                  minLength={3}
                  required
                />
              </div>

              <div>
                <label htmlFor="contact-message" className="field-label">
                  Message
                </label>
                <textarea
                  id="contact-message"
                  className="textarea"
                  rows={5}
                  value={messageBody}
                  onChange={(event) => setMessageBody(event.target.value)}
                  minLength={10}
                  required
                />
              </div>

              {contactMutation.isError && (
                <div className="notice-banner error" role="alert">
                  <span>{contactMutation.error.message}</span>
                </div>
              )}

              <button
                type="submit"
                className="btn btn-primary"
                disabled={contactMutation.isPending}
              >
                {contactMutation.isPending ? "Sending..." : "Send Message ->"}
              </button>
            </form>
          )}
        </section>
      </main>

      <UtilitiesFooter />
    </div>
  );
}
