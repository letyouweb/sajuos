import { NextResponse } from "next/server";

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function GET() {
  try {
    const response = await fetch(`${BACKEND_URL}/health`, {
      method: "GET",
      cache: "no-store",
    });

    const data = await response.json().catch(() => ({ status: "unknown" }));
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    console.error("Health check proxy error:", error);
    return NextResponse.json({ status: "backend_unreachable" }, { status: 500 });
  }
}
