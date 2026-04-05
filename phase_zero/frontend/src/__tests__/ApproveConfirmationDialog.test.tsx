/**
 * ApproveConfirmationDialog — Tests (DLG-01 → DLG-05)
 *
 * Tests dialog rendering, session_id display, and button callbacks.
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ApproveConfirmationDialog } from "../components/ApproveConfirmationDialog";

describe("ApproveConfirmationDialog", () => {
  const mockConfirm = vi.fn();
  const mockCancel = vi.fn();

  // DLG-01: renders dialog overlay
  it("DLG-01 renders dialog overlay", () => {
    render(
      <ApproveConfirmationDialog
        sessionId="sess-1"
        onConfirm={mockConfirm}
        onCancel={mockCancel}
      />
    );
    expect(screen.getByTestId("approve-dialog-overlay")).toBeInTheDocument();
    expect(screen.getByTestId("approve-dialog")).toBeInTheDocument();
  });

  // DLG-02: displays session_id
  it("DLG-02 displays session_id", () => {
    render(
      <ApproveConfirmationDialog
        sessionId="sess-99"
        onConfirm={mockConfirm}
        onCancel={mockCancel}
      />
    );
    expect(screen.getByTestId("dialog-session-id")).toHaveTextContent(
      "Session ID: sess-99"
    );
  });

  // DLG-03: confirm button calls onConfirm
  it("DLG-03 confirm button calls onConfirm", () => {
    const onConfirm = vi.fn();
    render(
      <ApproveConfirmationDialog
        sessionId="sess-1"
        onConfirm={onConfirm}
        onCancel={mockCancel}
      />
    );
    fireEvent.click(screen.getByTestId("confirm-approve-button"));
    expect(onConfirm).toHaveBeenCalledOnce();
  });

  // DLG-04: cancel button calls onCancel
  it("DLG-04 cancel button calls onCancel", () => {
    const onCancel = vi.fn();
    render(
      <ApproveConfirmationDialog
        sessionId="sess-1"
        onConfirm={mockConfirm}
        onCancel={onCancel}
      />
    );
    fireEvent.click(screen.getByTestId("cancel-button"));
    expect(onCancel).toHaveBeenCalledOnce();
  });

  // DLG-05: warning text present
  it("DLG-05 warning text present", () => {
    render(
      <ApproveConfirmationDialog
        sessionId="sess-1"
        onConfirm={mockConfirm}
        onCancel={mockCancel}
      />
    );
    expect(screen.getByTestId("approve-dialog")).toHaveTextContent(
      "This action is final"
    );
  });
});
