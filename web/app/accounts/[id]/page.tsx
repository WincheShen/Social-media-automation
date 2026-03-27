import { readAccount } from "@/lib/yaml-utils";
import { notFound } from "next/navigation";
import { AccountEditor } from "./account-editor";

export const dynamic = "force-dynamic";

export default async function AccountDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const account = readAccount(id);
  if (!account) notFound();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">
          编辑账号 — {account.persona?.name || id}
        </h1>
        <p className="text-muted-foreground mt-1">
          修改 Prompt、模型版本和其他配置
        </p>
      </div>
      <AccountEditor account={account} />
    </div>
  );
}
