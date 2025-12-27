"use client";

export default function Error({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 to-purple-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-lg p-8 max-w-lg w-full text-center">
        <div className="text-5xl mb-4">⚠️</div>
        <h2 className="text-xl font-bold text-red-700 mb-4">리포트 페이지 오류</h2>
        <pre className="text-left bg-red-50 p-4 rounded-lg text-sm text-red-600 overflow-auto max-h-40 mb-6 whitespace-pre-wrap">
          {error.message}
        </pre>
        <div className="space-x-4">
          <button
            onClick={() => reset()}
            className="px-6 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition"
          >
            다시 시도
          </button>
          <button
            onClick={() => window.location.href = '/'}
            className="px-6 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 transition"
          >
            홈으로
          </button>
        </div>
      </div>
    </div>
  );
}
