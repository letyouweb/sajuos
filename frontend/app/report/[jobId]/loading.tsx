export default function Loading() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 to-purple-50 flex items-center justify-center">
      <div className="text-center">
        <div className="w-16 h-16 border-4 border-purple-200 border-t-purple-600 rounded-full animate-spin mb-6 mx-auto" />
        <p className="text-slate-600 text-lg">리포트 불러오는 중...</p>
      </div>
    </div>
  );
}
