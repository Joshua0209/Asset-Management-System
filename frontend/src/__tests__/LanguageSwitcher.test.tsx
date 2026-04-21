import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { LanguageSwitcher } from "../components/LanguageSwitcher";
import i18n from "../i18n";

describe("LanguageSwitcher", () => {
  afterEach(async () => {
    await i18n.changeLanguage("en");
  });

  it("renders both 中 and EN buttons", () => {
    render(<LanguageSwitcher />);
    expect(screen.getByRole("button", { name: "中" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "EN" })).toBeInTheDocument();
  });

  it("marks the current language as active via aria-pressed", () => {
    render(<LanguageSwitcher />);
    expect(screen.getByRole("button", { name: "EN" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "中" })).toHaveAttribute("aria-pressed", "false");
  });

  it("switches language when the inactive button is clicked", async () => {
    const user = userEvent.setup();
    render(<LanguageSwitcher />);
    await user.click(screen.getByRole("button", { name: "中" }));
    expect(i18n.language).toBe("zh-TW");
  });
});
