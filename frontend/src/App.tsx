import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createBrowserRouter, RouterProvider, type RouteObject } from "react-router-dom";

import { AppShell } from "@/components/layout/AppShell";
import { PreferencesProvider } from "@/hooks/usePreferences";
import { ToastProvider } from "@/hooks/useToast";
import { AssistantPage } from "@/pages/AssistantPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { DocumentsPage } from "@/pages/DocumentsPage";
import { DocumentViewerPage } from "@/pages/DocumentViewerPage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { WorkspaceDetailPage } from "@/pages/WorkspaceDetailPage";
import { WorkspacesPage } from "@/pages/WorkspacesPage";
import { ApiError } from "@/services/api";

export const routes: RouteObject[] = [
  {
    element: <AppShell />,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: "workspaces", element: <WorkspacesPage /> },
      { path: "workspaces/:workspaceId", element: <WorkspaceDetailPage /> },
      { path: "documents", element: <DocumentsPage /> },
      { path: "documents/:documentId", element: <DocumentViewerPage /> },
      { path: "assistant", element: <AssistantPage /> },
      { path: "settings", element: <SettingsPage /> },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];

export function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 15_000,
        refetchOnWindowFocus: false,
        // Do not retry client errors such as 404.
        retry: (count, error) => !(error instanceof ApiError && error.status >= 400 && error.status < 500) && count < 2,
      },
    },
  });
}

export function Providers({ client, children }: { client: QueryClient; children: React.ReactNode }) {
  return (
    <QueryClientProvider client={client}>
      <PreferencesProvider>
        <ToastProvider>{children}</ToastProvider>
      </PreferencesProvider>
    </QueryClientProvider>
  );
}

const router = createBrowserRouter(routes, {
  future: { v7_relativeSplatPath: true, v7_fetcherPersist: true, v7_normalizeFormMethod: true, v7_partialHydration: true, v7_skipActionErrorRevalidation: true },
});
const queryClient = createQueryClient();

export default function App() {
  return (
    <Providers client={queryClient}>
      <RouterProvider router={router} future={{ v7_startTransition: true }} />
    </Providers>
  );
}
