import React from "react";
import { ApiError } from "../api/client";
import { getErrorMessage } from "../api/errors";

interface ErrorAlertProps {
  error: unknown;
  onDismiss?: () => void;
  className?: string;
}

export const ErrorAlert: React.FC<ErrorAlertProps> = ({
  error,
  onDismiss,
  className = "",
}) => {
  if (!error) return null;

  let message = "";
  let code: string | null = null;

  if (error instanceof ApiError) {
    code = error.code;
    message = getErrorMessage(error.code, error.message);
  } else if (error instanceof Error) {
    message = error.message;
  } else if (typeof error === "string") {
    message = error;
  } else {
    message = getErrorMessage();
  }

  return (
    <div
      role="alert"
      className={`rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800 ${className}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2">
          <svg
            className="h-5 w-5 flex-shrink-0 text-red-500 mt-0.5"
            viewBox="0 0 20 20"
            fill="currentColor"
            aria-hidden="true"
          >
            <path
              fillRule="evenodd"
              d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z"
              clipRule="evenodd"
            />
          </svg>
          <div>
            {code && (
              <span className="font-semibold uppercase tracking-wider text-xs text-red-600 block mb-1">
                Error: {code}
              </span>
            )}
            <p className="font-medium">{message}</p>
          </div>
        </div>
        {onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            className="rounded p-1 text-red-500 hover:bg-red-100 hover:text-red-700 focus:outline-none"
            aria-label="Dismiss error"
          >
            <span aria-hidden="true">&times;</span>
          </button>
        )}
      </div>
    </div>
  );
};
