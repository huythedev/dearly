import { createRoot } from 'react-dom/client';
import { Preferences } from './i18n';
import { App } from './App';
import './styles.css';

createRoot(document.getElementById('root')!).render(<Preferences><App /></Preferences>);
