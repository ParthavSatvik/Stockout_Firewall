import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { PageHeader } from "../../components/supplier/parts";
import { ErrorState, SkeletonCard } from "../../components/ui/state";
import { api } from "../../lib/api";
import type { Passport } from "../../lib/continuity";
import { PassportView } from "./PassportPage";

/** Merchant-facing, order-free view of a supplier's Trust Passport. */
export function NetworkPassportPage() {
  const { supplierId } = useParams<{ supplierId: string }>();
  const q = useQuery({ queryKey: ["network-passport", supplierId], queryFn: () => api.get<Passport>(`/api/network/suppliers/${supplierId}/passport`), enabled: !!supplierId });
  return (
    <div className="space-y-5">
      <PageHeader eyebrow="Supplier Trust Passport" title={q.data?.supplier_name ?? "Supplier passport"}>
        Aggregate evidence from this supplier's recorded commitments across the network. No other merchant's orders are shown.
      </PageHeader>
      {q.isPending && <SkeletonCard />}
      {q.isError && <ErrorState message="Passport unavailable." />}
      {q.data && <PassportView data={q.data} />}
    </div>
  );
}
