import { useCallback } from 'react';
import { api } from '../api';
import { ErrorState, LoadingState } from '../components';
import { CommercialMethod } from '../components/CommercialMatrix';
import { RulesCoverage } from '../components/RulesCoverage';
import { useApiResource } from '../hooks/useApiResource';
import { usePageLoadStatus } from '../hooks/usePageLoadStatus';
import { AuditoriaContent } from './ValidationPage';

export default function AuditoriaPage({ refreshToken }: { refreshToken: number }) {
  const loader = useCallback(async (signal: AbortSignal) => {
    // A cobertura é um bloco a mais: se ela falhar, o resto da auditoria continua disponível.
    const [summary, partners, coverage] = await Promise.all([api.validationSummary(signal), api.partners(new URLSearchParams({ limit: '1' }), signal), api.rulesCoverage(signal).catch(() => null)]);
    return { summary, partners, coverage };
  }, []);
  const { data, error, loading, loadedAt, refresh } = useApiResource(loader, refreshToken);
  usePageLoadStatus(loading, error, loadedAt);
  if (!data && error) return <ErrorState message={error} onRetry={() => void refresh()} />;
  if (!data) return <LoadingState />;
  return <AuditoriaContent data={data.summary} coverage={data.coverage ? <RulesCoverage data={data.coverage} /> : undefined} method={<CommercialMethod response={data.partners} />} />;
}
