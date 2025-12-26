'use client';

import { useState } from 'react';
import { 
  CONCERN_OPTIONS, 
  HOUR_OPTIONS,
  getHourFromJiIndex,
  type ConcernType 
} from '@/types';

interface SajuFormProps {
  onSubmit: (data: {
    name: string;
    email: string;  // 🔥 이메일 추가
    birthYear: number;
    birthMonth: number;
    birthDay: number;
    birthHour: number | null;
    birthMinute: number;
    gender: 'male' | 'female' | 'other';
    concernType: ConcernType;
    question: string;
  }) => void;
}

export default function SajuForm({ onSubmit }: SajuFormProps) {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');  // 🔥 이메일 상태
  const [birthYear, setBirthYear] = useState(1990);
  const [birthMonth, setBirthMonth] = useState(1);
  const [birthDay, setBirthDay] = useState(1);
  const [knowHour, setKnowHour] = useState(false);
  const [hourJiIndex, setHourJiIndex] = useState<number>(6);
  const [gender, setGender] = useState<'male' | 'female' | 'other'>('female');
  const [concernType, setConcernType] = useState<ConcernType>('career');
  const [question, setQuestion] = useState('');
  const [emailError, setEmailError] = useState('');

  const validateEmail = (email: string): boolean => {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    
    // 이메일 유효성 검사
    if (!email) {
      setEmailError('이메일을 입력해주세요.');
      return;
    }
    if (!validateEmail(email)) {
      setEmailError('올바른 이메일 형식을 입력해주세요.');
      return;
    }
    setEmailError('');
    
    const birthHour = knowHour ? getHourFromJiIndex(hourJiIndex) : null;
    
    onSubmit({
      name: name || '고객님',
      email,
      birthYear,
      birthMonth,
      birthDay,
      birthHour,
      birthMinute: 0,
      gender,
      concernType,
      question: question || '올해 사업 운영에서 가장 집중해야 할 영역이 궁금합니다.',
    });
  };

  const currentYear = new Date().getFullYear();

  return (
    <form onSubmit={handleSubmit} className="bg-white rounded-2xl shadow-lg p-6 md:p-8 animate-fade-in-up">
      <h2 className="text-2xl font-bold text-gray-800 mb-6 flex items-center gap-2">
        <span>📝</span> 프리미엄 비즈니스 보고서 신청
      </h2>

      {/* 🔥 이메일 (필수) */}
      <div className="mb-6">
        <label className="block text-sm font-medium text-gray-700 mb-2">
          이메일 <span className="text-red-500">*</span>
          <span className="text-xs text-gray-500 ml-2">(보고서 완료 알림 발송)</span>
        </label>
        <input
          type="email"
          value={email}
          onChange={(e) => {
            setEmail(e.target.value);
            setEmailError('');
          }}
          placeholder="your@email.com"
          className={`w-full px-4 py-3 border rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent transition ${
            emailError ? 'border-red-400 bg-red-50' : 'border-gray-200'
          }`}
        />
        {emailError && (
          <p className="text-red-500 text-sm mt-1">{emailError}</p>
        )}
        <p className="text-xs text-gray-500 mt-1">
          💡 창을 닫아도 백그라운드에서 생성이 계속됩니다. 완료되면 이메일로 알려드려요.
        </p>
      </div>

      {/* 이름 */}
      <div className="mb-6">
        <label className="block text-sm font-medium text-gray-700 mb-2">
          이름 (닉네임)
        </label>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="홍길동"
          className="w-full px-4 py-3 border border-gray-200 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent transition"
        />
      </div>

      {/* 생년월일 */}
      <div className="mb-6">
        <label className="block text-sm font-medium text-gray-700 mb-2">
          생년월일 (양력)
        </label>
        <div className="grid grid-cols-3 gap-3">
          <div>
            <select
              value={birthYear}
              onChange={(e) => setBirthYear(Number(e.target.value))}
              className="w-full px-3 py-3 border border-gray-200 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent"
            >
              {Array.from({ length: 100 }, (_, i) => currentYear - i).map((year) => (
                <option key={year} value={year}>{year}년</option>
              ))}
            </select>
          </div>
          <div>
            <select
              value={birthMonth}
              onChange={(e) => setBirthMonth(Number(e.target.value))}
              className="w-full px-3 py-3 border border-gray-200 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent"
            >
              {Array.from({ length: 12 }, (_, i) => i + 1).map((month) => (
                <option key={month} value={month}>{month}월</option>
              ))}
            </select>
          </div>
          <div>
            <select
              value={birthDay}
              onChange={(e) => setBirthDay(Number(e.target.value))}
              className="w-full px-3 py-3 border border-gray-200 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent"
            >
              {Array.from({ length: 31 }, (_, i) => i + 1).map((day) => (
                <option key={day} value={day}>{day}일</option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* 출생 시간 */}
      <div className="mb-6">
        <div className="flex items-center mb-3">
          <input
            type="checkbox"
            id="knowHour"
            checked={knowHour}
            onChange={(e) => setKnowHour(e.target.checked)}
            className="w-4 h-4 text-purple-600 border-gray-300 rounded focus:ring-purple-500"
          />
          <label htmlFor="knowHour" className="ml-2 text-sm font-medium text-gray-700">
            출생시간을 알고 있어요
          </label>
        </div>
        
        {knowHour && (
          <div className="space-y-3">
            <select
              value={hourJiIndex}
              onChange={(e) => setHourJiIndex(Number(e.target.value))}
              className="w-full px-3 py-3 border border-gray-200 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent text-base"
            >
              {HOUR_OPTIONS.map((option) => (
                <option key={option.index} value={option.index}>
                  {option.ji_hanja}시 ({option.ji}시) - {option.range_start}~{option.range_end}
                </option>
              ))}
            </select>
            
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
              <p className="text-sm text-blue-700">
                ℹ️ 시주는 2시간 단위로 계산됩니다.
              </p>
            </div>
          </div>
        )}
        
        {!knowHour && (
          <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
            <p className="text-sm text-amber-700">
              ⚠️ 시간 미입력시 시주 분석이 생략됩니다.
            </p>
          </div>
        )}
      </div>

      {/* 성별 */}
      <div className="mb-6">
        <label className="block text-sm font-medium text-gray-700 mb-2">
          성별
        </label>
        <div className="flex gap-3">
          {[
            { value: 'male', label: '남성', emoji: '👨' },
            { value: 'female', label: '여성', emoji: '👩' },
          ].map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => setGender(option.value as 'male' | 'female')}
              className={`flex-1 py-3 px-4 rounded-lg border-2 transition ${
                gender === option.value
                  ? 'border-purple-500 bg-purple-50 text-purple-700'
                  : 'border-gray-200 hover:border-gray-300'
              }`}
            >
              <span className="mr-2">{option.emoji}</span>
              {option.label}
            </button>
          ))}
        </div>
      </div>

      {/* 고민 유형 */}
      <div className="mb-6">
        <label className="block text-sm font-medium text-gray-700 mb-2">
          분석 집중 분야
        </label>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
          {CONCERN_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => setConcernType(option.value)}
              className={`py-3 px-4 rounded-lg border-2 text-sm transition ${
                concernType === option.value
                  ? 'border-purple-500 bg-purple-50 text-purple-700'
                  : 'border-gray-200 hover:border-gray-300'
              }`}
            >
              <span className="mr-1">{option.emoji}</span>
              {option.label}
            </button>
          ))}
        </div>
      </div>

      {/* 질문 */}
      <div className="mb-6">
        <label className="block text-sm font-medium text-gray-700 mb-2">
          구체적인 상황/질문 (선택)
        </label>
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="예: 올해 신규 사업을 시작하려 합니다. 최적의 시기와 주의사항이 궁금합니다."
          rows={3}
          className="w-full px-4 py-3 border border-gray-200 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent resize-none"
        />
      </div>

      {/* 면책조항 */}
      <div className="mb-4 bg-gray-50 border border-gray-200 rounded-lg p-3">
        <p className="text-xs text-gray-500">
          ⚠️ 본 서비스는 <strong>참고/컨설팅 목적</strong>으로 제공됩니다. 
          법률/투자/의료 등 전문적 조언을 대체하지 않습니다.
        </p>
      </div>

      {/* 제출 버튼 */}
      <button
        type="submit"
        className="w-full py-4 bg-gradient-to-r from-purple-600 to-purple-700 hover:from-purple-700 hover:to-purple-800 text-white font-bold text-lg rounded-xl shadow-lg hover:shadow-xl transition transform hover:-translate-y-0.5"
      >
        💎 프리미엄 보고서 생성하기
      </button>
      
      {/* 가격 안내 */}
      <p className="text-center text-sm text-gray-500 mt-3">
        ✨ 7개 섹션 · 약 30페이지 분량 · 완료 시 이메일 발송
      </p>
    </form>
  );
}
