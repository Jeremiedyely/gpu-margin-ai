/**
 * Progress Stepper — visual pipeline indicator.
 *
 * 4 steps: Upload → Analyze → Approve → Export
 * Each step is done, active, or pending based on application state.
 */

interface Step {
  label: string;
  state: "done" | "active" | "pending";
}

interface ProgressStepperProps {
  currentStep: 1 | 2 | 3 | 4;
}

const LABELS = ["Upload", "Analyze", "Approve", "Export"];

export function ProgressStepper({ currentStep }: ProgressStepperProps) {
  const steps: Step[] = LABELS.map((label, i) => {
    const num = i + 1;
    if (num < currentStep) return { label, state: "done" };
    if (num === currentStep) return { label, state: "active" };
    return { label, state: "pending" };
  });

  return (
    <div className="flex items-center justify-center gap-0 my-6">
      {steps.map((step, i) => (
        <div key={step.label} className="flex items-center">
          {/* Step */}
          <div className="flex flex-col items-center gap-1">
            <div
              className={`w-9 h-9 rounded-full flex items-center justify-center text-sm font-bold border-2 transition-all ${
                step.state === "done"
                  ? "bg-emerald-500 border-emerald-500 text-white"
                  : step.state === "active"
                    ? "bg-blue-500 border-blue-500 text-white"
                    : "bg-white border-slate-200 text-slate-400"
              }`}
            >
              {step.state === "done" ? "✓" : i + 1}
            </div>
            <span
              className={`text-xs font-medium transition-all ${
                step.state === "done"
                  ? "text-emerald-700"
                  : step.state === "active"
                    ? "text-blue-600 font-semibold"
                    : "text-slate-400"
              }`}
            >
              {step.label}
            </span>
          </div>

          {/* Connector line (except after last) */}
          {i < steps.length - 1 && (
            <div
              className={`w-14 h-0.5 mx-2 mb-5 transition-all ${
                steps[i + 1].state === "done" || step.state === "done"
                  ? "bg-emerald-400"
                  : "bg-slate-200"
              }`}
            />
          )}
        </div>
      ))}
    </div>
  );
}
