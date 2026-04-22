import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { LanguageSwitcher } from "../components/LanguageSwitcher";
import i18n from "../i18n";

describe("LanguageSwitcher", () => {
  afterEach(async () => {
    await act(async () => {
      await i18n.changeLanguage("en");
    });
  });

  it("renders both 中 and EN options", async () => {
    await act(async () => {
      render(<LanguageSwitcher />);
    });
    expect(screen.getByText("中")).toBeInTheDocument();
    expect(screen.getByText("EN")).toBeInTheDocument();
  });

  it("marks the current language as selected", async () => {
    await act(async () => {
      render(<LanguageSwitcher />);
    });
    // Ant Design Segmented component uses radio roles for the selection
    const enOption = screen.getByRole("radio", { name: "EN" });
    const zhOption = screen.getByRole("radio", { name: "中" });

    expect(enOption).toBeChecked();
    expect(zhOption).not.toBeChecked();
  });

  it("switches language when the inactive option is clicked", async () => {
    const user = userEvent.setup();
    await act(async () => {
      render(<LanguageSwitcher />);
    });

    // Click on the label for "中"
    const zhOptionLabel = screen.getByText("中");
    await act(async () => {
      await user.click(zhOptionLabel);
    });

    await waitFor(() => {
      expect(i18n.language).toBe("zh");
    });

    const enOption = screen.getByRole("radio", { name: "EN" });
    const zhOption = screen.getByRole("radio", { name: "中" });

    expect(zhOption).toBeChecked();
    expect(enOption).not.toBeChecked();
  });
});
