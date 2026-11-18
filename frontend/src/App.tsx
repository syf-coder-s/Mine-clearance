import { AppRouter } from './app/router';
import { HealthProvider } from './app/HealthProvider';

export default function App() {
  return (
    <HealthProvider>
      <AppRouter />
    </HealthProvider>
  );
}