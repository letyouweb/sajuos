import { NextResponse } from "next/server";

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function GET() {
  try {
    const response = await fetch(`${BACKEND_URL}/api/v1/calculate/hour-options`, {
      method: "GET",
      headers: { "Content-Type": "application/json" },
      cache: "no-store",
    });

    const data = await response.json().catch(() => []);
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    console.error("Hour options proxy error:", error);
    return NextResponse.json([], { status: 500 });
  }
}
