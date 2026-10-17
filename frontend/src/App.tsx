import { lazy, Suspense, type ReactNode } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppShell, RequireAuth } from "./components/AppShell";
import { ToastProvider } from "./components/ui/toast";
import { AuthProvider, useAuth } from "./lib/auth";
import { I18nProvider, useT } from "./lib/i18n";
import { ThemeProvider } from "./lib/theme";
const AdminDashboard = lazy(() => import("./pages/AdminDashboard").then(m => ({ default: m.AdminDashboard })));
const LoginPage = lazy(() => import("./pages/LoginPage").then(m => ({ default: m.LoginPage })));
const MerchantHomePage = lazy(() => import("./pages/MerchantHomePage").then(m => ({ default: m.MerchantHomePage })));
const MerchantOrdersPage = lazy(() => import("./pages/MerchantOrdersPage").then(m => ({ default: m.MerchantOrdersPage })));
const NewOrderPage = lazy(() => import("./pages/NewOrderPage").then(m => ({ default: m.NewOrderPage })));
const OrderDetailPage = lazy(() => import("./pages/OrderDetailPage").then(m => ({ default: m.OrderDetailPage })));
const CopilotPage = lazy(() => import("./pages/supplier/CopilotPage").then(m => ({ default: m.CopilotPage })));
const RequestsPage = lazy(() => import("./pages/supplier/RequestsPage").then(m => ({ default: m.RequestsPage })));
const DispatchPage = lazy(() => import("./pages/supplier/DispatchPage").then(m => ({ default: m.DispatchPage })));
const RelayPage = lazy(() => import("./pages/supplier/RelayPage").then(m => ({ default: m.RelayPage })));
const LedgerPage = lazy(() => import("./pages/supplier/LedgerPage").then(m => ({ default: m.LedgerPage })));
const PassportPage = lazy(() => import("./pages/supplier/PassportPage").then(m => ({ default: m.PassportPage })));
const NetworkPassportPage = lazy(() => import("./pages/supplier/NetworkPassportPage").then(m => ({ default: m.NetworkPassportPage })));
const SupplierInventoryPage = lazy(() => import("./pages/SupplierInventoryPage").then(m => ({ default: m.SupplierInventoryPage })));
const AutopilotPage = lazy(() => import("./pages/intelligence/AutopilotPage").then(m => ({ default: m.AutopilotPage })));
const CashCyclePage = lazy(() => import("./pages/intelligence/CashCyclePage").then(m => ({ default: m.CashCyclePage })));
const DeadStockExchangePage = lazy(() => import("./pages/intelligence/DeadStockExchangePage").then(m => ({ default: m.DeadStockExchangePage })));
const MarginLeakPage = lazy(() => import("./pages/intelligence/MarginLeakPage").then(m => ({ default: m.MarginLeakPage })));
const PriceIndexPage = lazy(() => import("./pages/intelligence/PriceIndexPage").then(m => ({ default: m.PriceIndexPage })));
const StockoutRadarPage = lazy(() => import("./pages/intelligence/StockoutRadarPage").then(m => ({ default: m.StockoutRadarPage })));
const SurvivalModePage = lazy(() => import("./pages/intelligence/SurvivalModePage").then(m => ({ default: m.SurvivalModePage })));

function LoadingPage() {
  const { t } = useT();
  return <p role="status">{t("common.loadingPage")}</p>;
}

function Home() {
  const { isAuthenticated, role } = useAuth();
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  if (role === "merchant") return <Navigate to="/merchant" replace />;
  if (role === "supplier") return <Navigate to="/supplier" replace />;
  if (role === "admin") return <Navigate to="/admin" replace />;
  return <Navigate to="/login" replace />;
}

function Protected({ role, children }: { role: string; children: ReactNode }) {
  return <RequireAuth allowedRoles={[role]}>{children}</RequireAuth>;
}

export default function App() {
  return (
    <ThemeProvider>
      <I18nProvider>
      <ToastProvider>
        <BrowserRouter>
          <AuthProvider>
            <AppShell>
              <Suspense fallback={<LoadingPage />}><Routes>
                <Route path="/" element={<Home />} />
                <Route path="/login" element={<LoginPage />} />

                <Route path="/merchant" element={<Protected role="merchant"><MerchantHomePage /></Protected>} />
                <Route path="/merchant/orders" element={<Protected role="merchant"><MerchantOrdersPage /></Protected>} />
                <Route path="/merchant/new" element={<Protected role="merchant"><NewOrderPage /></Protected>} />
                <Route path="/merchant/orders/:orderId" element={<Protected role="merchant"><OrderDetailPage /></Protected>} />
                <Route path="/merchant/intelligence/stockout-radar" element={<Protected role="merchant"><StockoutRadarPage /></Protected>} />
                <Route path="/merchant/intelligence/survival-mode" element={<Protected role="merchant"><SurvivalModePage /></Protected>} />
                <Route path="/merchant/intelligence/cash-cycle" element={<Protected role="merchant"><CashCyclePage /></Protected>} />
                <Route path="/merchant/intelligence/margin-leak" element={<Protected role="merchant"><MarginLeakPage /></Protected>} />
                <Route path="/merchant/intelligence/price-index" element={<Protected role="merchant"><PriceIndexPage /></Protected>} />
                <Route path="/merchant/intelligence/autopilot" element={<Protected role="merchant"><AutopilotPage /></Protected>} />
                <Route path="/merchant/intelligence/dead-stock" element={<Protected role="merchant"><DeadStockExchangePage /></Protected>} />

                <Route path="/merchant/suppliers/:supplierId/passport" element={<Protected role="merchant"><NetworkPassportPage /></Protected>} />

                <Route path="/supplier" element={<Protected role="supplier"><CopilotPage /></Protected>} />
                <Route path="/supplier/requests" element={<Protected role="supplier"><RequestsPage /></Protected>} />
                <Route path="/supplier/dispatch" element={<Protected role="supplier"><DispatchPage /></Protected>} />
                <Route path="/supplier/relay" element={<Protected role="supplier"><RelayPage /></Protected>} />
                <Route path="/supplier/ledger" element={<Protected role="supplier"><LedgerPage /></Protected>} />
                <Route path="/supplier/passport" element={<Protected role="supplier"><PassportPage /></Protected>} />
                <Route path="/supplier/inventory" element={<Protected role="supplier"><SupplierInventoryPage /></Protected>} />
                <Route path="/supplier/dead-stock" element={<Protected role="supplier"><DeadStockExchangePage /></Protected>} />

                <Route path="/admin" element={<Protected role="admin"><AdminDashboard /></Protected>} />

                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes></Suspense>
            </AppShell>
          </AuthProvider>
        </BrowserRouter>
      </ToastProvider>
      </I18nProvider>
    </ThemeProvider>
  );
}
