import type { Metadata } from 'next';
import './globals.css';

// 환경변수에서 브랜딩 정보 로드 (Vercel 설정값 우선)
const BRAND_NAME = process.env.NEXT_PUBLIC_BRAND_NAME ?? '사주퀸';
const BRAND_TAGLINE = process.env.NEXT_PUBLIC_BRAND_TAGLINE ?? '당신의 인생 매뉴얼';
const BRAND_DESC = process.env.NEXT_PUBLIC_BRAND_DESC ?? '데이터로 읽는 당신의 운명 분석 서비스, 사주퀸입니다.';

// 실제 배포 주소 (Vercel Metadata 경고 해결용)
const BASE_URL = process.env.NODE_ENV === 'production' 
  ? 'https://sajuqueen.com' 
  : 'http://localhost:3000';

export const metadata: Metadata = {
  // [1] SEO 경고 해결: 기준 URL 설정
  metadataBase: new URL(BASE_URL),
  
  title: {
    default: `${BRAND_NAME} - ${BRAND_TAGLINE}`,
    template: `%s | ${BRAND_NAME}`
  },
  description: BRAND_DESC,
  keywords: ['사주', '운세', '명리학', 'AI', '인공지능', '팔자', '사주풀이', '만세력', '사주OS'],
  
  // [2] 파비콘 404 에러 방지 설정
  icons: {
    icon: '/favicon.ico',
    shortcut: '/favicon.ico',
    apple: '/apple-icon.png',
  },

  // [3] 소셜 공유(OG) 설정
  openGraph: {
    title: `${BRAND_NAME} - ${BRAND_TAGLINE}`,
    description: BRAND_DESC,
    url: BASE_URL,
    siteName: BRAND_NAME,
    images: [
      {
        url: '/og-image.png', // public 폴더에 해당 이미지가 있어야 합니다.
        width: 1200,
        height: 630,
        alt: `${BRAND_NAME} 메인 이미지`,
      },
    ],
    locale: 'ko_KR',
    type: 'website',
  },
  twitter: {
    card: 'summary_large_image',
    title: `${BRAND_NAME} - ${BRAND_TAGLINE}`,
    description: BRAND_DESC,
    images: ['/og-image.png'],
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const currentYear = new Date().getFullYear();
  
  return (
    <html lang="ko">
      <head>
        {/* 프리텐다드 폰트 적용 */}
        <link
          rel="stylesheet"
          as="style"
          crossOrigin="anonymous"
          href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css"
        />
      </head>
      {/* [4] 가독성 개선: text-slate-900으로 기본 글자색을 진하게 설정 
        배경색: 기존의 고급스러운 그라데이션 유지
      */}
      <body className="min-h-screen bg-gradient-to-br from-purple-50 via-white to-amber-50 text-slate-900 antialiased selection:bg-purple-100">
        <main className="container mx-auto px-4 py-8 max-w-4xl min-h-[calc(100vh-160px)]">
          {children}
        </main>
        
        {/* [5] 푸터 디자인 정돈 */}
        <footer className="text-center py-10 border-t border-slate-100 text-slate-500 text-xs md:text-sm">
          <div className="container mx-auto px-4">
            <p className="mb-3 leading-relaxed max-w-2xl mx-auto">
              ⚠️ 본 서비스는 오락/참고 목적으로 제공되며, 의학/법률/투자 등 전문적 조언을 대체하지 않습니다. 
              분석 결과에 따른 최종 결정은 본인에게 있습니다.
            </p>
            <p className="font-medium">
              © {currentYear} <strong>{BRAND_NAME}</strong>. All rights reserved.
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}