import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import { ScenariosView } from "./ScenariosView";
import { handlers } from "../../mocks/handlers";

const server = setupServer(...handlers);

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("ScenariosView", () => {
  it("renders scenario list from API", async () => {
    const handleStart = vi.fn();
    render(<ScenariosView onSessionStarted={handleStart} />);

    expect(screen.getByText(/loading scenarios/i)).toBeInTheDocument();

    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: "Behavioral Job Interview" }),
      ).toBeInTheDocument();
    });
    expect(screen.getByText("2-on-1 Panel")).toBeInTheDocument();
    expect(screen.getByText("AI #1: Alex")).toBeInTheDocument();
    expect(screen.getByText("AI #2: Sarah")).toBeInTheDocument();
  });

  it("views scenario detail and starts practice session", async () => {
    const handleStart = vi.fn();
    render(<ScenariosView onSessionStarted={handleStart} />);

    await waitFor(() => {
      expect(screen.getByText("Behavioral Job Interview")).toBeInTheDocument();
    });

    // Click "View Details"
    fireEvent.click(screen.getByRole("button", { name: /view details/i }));

    // Verify detail is shown
    await waitFor(() => {
      expect(screen.getByText("2-on-1 Panel")).toBeInTheDocument();
      expect(screen.getByText("Alex")).toBeInTheDocument();
      expect(screen.getByText("Sarah")).toBeInTheDocument();
      expect(screen.getByText("Engineering Manager")).toBeInTheDocument();
      expect(screen.getByText("People Partner")).toBeInTheDocument();
    });

    // Click "Start Practice Session"
    const startBtn = screen.getByRole("button", {
      name: /start practice session/i,
    });
    fireEvent.click(startBtn);

    await waitFor(() => {
      expect(handleStart).toHaveBeenCalledTimes(1);
    });
  });

  it("handles API error when loading scenarios", async () => {
    server.use(
      http.get("*/api/v1/scenarios", () => {
        return HttpResponse.json(
          {
            error: {
              code: "INTERNAL_ERROR",
              message: "Database failed",
              details: null,
              request_id: "req_err",
            },
          },
          { status: 500 },
        );
      }),
    );

    render(<ScenariosView onSessionStarted={vi.fn()} />);

    await waitFor(() => {
      expect(
        screen.getByText(/an internal server error occurred/i),
      ).toBeInTheDocument();
    });
  });
});
