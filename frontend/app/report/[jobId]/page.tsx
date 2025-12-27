import ReportClient from "./report-client";

interface PageProps {
  params: Promise<{ jobId: string }>;
  searchParams: Promise<{ token?: string }>;
}

export default async function Page({ params, searchParams }: PageProps) {
  const { jobId } = await params;
  const { token } = await searchParams;
  
  return <ReportClient jobId={jobId} token={token || ""} />;
}
