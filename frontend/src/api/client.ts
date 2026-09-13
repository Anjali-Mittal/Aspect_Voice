// All backend calls go through here. Base URL comes from .env — nothing
// hardcoded, so the same build points at localhost in dev and Render in prod.
import axios from "axios";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export const api = axios.create({ baseURL: API_BASE_URL });

export async function checkHealth(): Promise<boolean> {
  try {
    const { data } = await api.get<{ status: string }>("/health", { timeout: 15000 });
    return data?.status === "ok";
  } catch {
    return false;
  }
}

export interface SentimentPct {
  positive: number;
  neutral: number;
  negative: number;
}

export interface OverviewKPIs {
  feedback_analyzed: number;
  sentiment_pct: SentimentPct;
  discovered_features: number;
  recurring_issues: number;
  high_priority_issues: number;
  emerging_issues: number;
}

export interface SentimentTrendPoint {
  month: string;
  positive: number;
  neutral: number;
  negative: number;
}

export interface TopStrength {
  feature: string;
  positive_pct: number;
  mentions: number;
}

export interface PainPoint {
  id: number;
  feature: string;
  issue: string;
  mentions: number;
  priority_score: number;
  trend: string;
}

export interface OverviewResponse {
  vehicle: string;
  kpis: OverviewKPIs;
  sentiment_trend: SentimentTrendPoint[];
  top_strengths: TopStrength[];
  top_pain_points: PainPoint[];
}

export interface MonthFeedbackTag {
  feature: string;
  sentiment: string | null;
  snippet: string | null;
}

export interface MonthFeedbackItem {
  full_text: string | null;
  author: string | null;
  source: string | null;
  url: string | null;
  published: string | null;
  tags: MonthFeedbackTag[];
}

export interface IssueSummary {
  id: number;
  feature: string;
  issue: string;
  mentions: number;
  avg_severity: number;
  safety_related: boolean;
  severity_bucket: "high" | "medium" | "low";
  priority_score: number;
  trend: string;
  confidence: number;
  confidence_basis: string; // "evidence_volume" — not a statistical measure
  examples: string[];
}

export interface IssueDetail {
  id: number;
  feature: string;
  issue: string;
  mentions: number;
  avg_severity: number;
  safety_related: boolean;
  severity_bucket: "high" | "medium" | "low";
  priority_score: number;
  trend: string;
  confidence: number;
  confidence_basis: string; // "evidence_volume" — not a statistical measure
  primary_context: string | null;
  recommended_investigation: string | null;
  source_group_count: number;
  monthly_trend: { month: string; count: number }[];
}

export interface EvidenceItem {
  observed: {
    full_text: string | null;
    author: string | null;
    source: string | null;
    url: string | null;
    published: string | null;
  };
  ai_interpretation: {
    snippet: string | null;
    sentiment: string | null;
    severity: number | null;
  };
}

export interface FeatureSummary {
  feature: string;
  mentions: number;
  sentiment_pct?: SentimentPct;
  severity_pct?: { high: number; medium: number; low: number };
  note?: string;
}

export async function fetchVehicles(): Promise<string[]> {
  const { data } = await api.get<string[]>("/vehicles");
  return data;
}

export async function fetchOverview(vehicle: string): Promise<OverviewResponse> {
  const { data } = await api.get<OverviewResponse>("/overview", { params: { vehicle } });
  return data;
}

export async function fetchFeedbackByMonth(vehicle: string, month: string): Promise<MonthFeedbackItem[]> {
  const { data } = await api.get<MonthFeedbackItem[]>("/feedback-by-month", { params: { vehicle, month } });
  return data;
}

export interface IssueFilters {
  feature?: string;
  trend?: string;
  severity?: string;
  min_priority?: number;
}

export async function fetchIssues(vehicle: string, filters: IssueFilters = {}): Promise<IssueSummary[]> {
  const { data } = await api.get<IssueSummary[]>("/issues", { params: { vehicle, ...filters } });
  return data;
}

export async function fetchIssueDetail(issueId: number): Promise<IssueDetail> {
  const { data } = await api.get<IssueDetail>(`/issues/${issueId}`);
  return data;
}

export async function fetchEvidence(issueId: number): Promise<EvidenceItem[]> {
  const { data } = await api.get<EvidenceItem[]>(`/issues/${issueId}/evidence`);
  return data;
}

export async function fetchFeatures(vehicle: string): Promise<{ feature: string; description: string }[]> {
  const { data } = await api.get(`/features`, { params: { vehicle } });
  return data;
}

export async function fetchFeatureSummary(feature: string, vehicle: string): Promise<FeatureSummary> {
  const { data } = await api.get<FeatureSummary>(`/features/${encodeURIComponent(feature)}/summary`, {
    params: { vehicle },
  });
  return data;
}