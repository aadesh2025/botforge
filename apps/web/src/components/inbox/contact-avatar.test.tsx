import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ContactAvatar, contactLabel } from "./contact-avatar";

describe("contactLabel", () => {
  it("prefers the contact's real name", () => {
    expect(contactLabel({ display_name: "Aadesh" }, "IG42")).toBe("Aadesh");
  });

  it("falls back to the channel id, truncated, when there's no contact yet", () => {
    expect(contactLabel(null, "178414000000000000999")).toBe("178414000000000000…");
    expect(contactLabel(null, "17841400000000000")).toBe("17841400000000000"); // exactly at the limit
    expect(contactLabel(null, "55")).toBe("55");
    expect(contactLabel(null, null)).toBe("Unknown contact");
  });
});

describe("ContactAvatar", () => {
  it("renders the photo when there is one", () => {
    const { container } = render(
      <ContactAvatar channel="instagram" name="Aadesh" avatarUrl="https://cdn/x.jpg" />,
    );
    expect(container.querySelector("img")).toHaveAttribute("src", "https://cdn/x.jpg");
  });

  it("names the contact and their platform for screen readers", () => {
    render(<ContactAvatar channel="instagram" name="Aadesh" />);
    expect(screen.getByText("Aadesh on Instagram")).toBeInTheDocument();
  });

  it("degrades to a person glyph when the platform gives no avatar", () => {
    const { container } = render(<ContactAvatar channel="whatsapp" name="Rohak" />);
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByText("Rohak on WhatsApp")).toBeInTheDocument();
  });
});
