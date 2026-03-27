import { NextResponse } from "next/server";
import { readAllAccounts } from "@/lib/yaml-utils";

export async function GET() {
  const accounts = readAllAccounts();
  return NextResponse.json(accounts);
}
