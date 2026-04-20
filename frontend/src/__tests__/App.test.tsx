import { render, screen } from "@testing-library/react";
import App from "../App";

describe("App", () => {
  it("renders the asset management system heading", () => {
    render(<App />);
    expect(screen.getByText(/Asset Management System/i)).toBeInTheDocument();
  });

  it("renders API docs link", () => {
    render(<App />);
    expect(screen.getByRole("link", { name: /open api docs/i })).toHaveAttribute(
      "href",
      "http://localhost:8000/docs"
    );
  });
});
