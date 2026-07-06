import { createContext, useContext, useMemo, useReducer, type Dispatch, type ReactNode } from "react";
import type { WidgetAction } from "./widgetActions";
import { widgetReducer } from "./widgetReducer";
import type { WidgetState } from "./widgetState";

type WidgetStateContextValue = {
  state: WidgetState;
  dispatch: Dispatch<WidgetAction>;
};

const WidgetStateContext = createContext<WidgetStateContextValue | undefined>(undefined);

export function WidgetStateProvider({
  initialState,
  children
}: {
  initialState: WidgetState;
  children: ReactNode;
}) {
  const [state, dispatch] = useReducer(widgetReducer, initialState);
  const value = useMemo(() => ({ state, dispatch }), [state]);

  return <WidgetStateContext.Provider value={value}>{children}</WidgetStateContext.Provider>;
}

export function useWidgetStateContext() {
  const context = useContext(WidgetStateContext);
  if (!context) {
    throw new Error("useWidgetStateContext must be used within WidgetStateProvider.");
  }
  return context;
}
