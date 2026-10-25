import { useAuth } from '@clerk/nextjs';
import Head from 'next/head';
import Layout from '../components/Layout';
import MarketPricePanel from '../components/MarketPricePanel';

export default function MarketData() {
  const { getToken, isLoaded, isSignedIn } = useAuth();
  return <Layout>
    <Head><title>Market Data | Alex</title></Head>
    <div className="max-w-6xl mx-auto px-4 sm:px-6 py-10">
      <h1 className="text-3xl font-bold text-gray-900">Market Data</h1>
      <p className="mt-3 mb-8 text-gray-600">Daily prices with a clear trading date and source.</p>
      <MarketPricePanel tokenProvider={getToken} enabled={isLoaded && !!isSignedIn} />
    </div>
  </Layout>;
}
