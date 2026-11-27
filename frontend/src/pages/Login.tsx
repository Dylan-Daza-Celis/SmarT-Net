import { FormEvent, useState } from 'react';
import { useSession } from '../auth/SessionProvider';
import { Notice } from '../components/ui';

export default function Login() {
  const { login, message } = useSession();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');

    try {
      await login(username, password);
    } catch (err) {
      setError(String(err instanceof Error ? err.message : err));
    } finally {
      setPassword('');
      setBusy(false);
    }
  }

  return (
    <div className="login-layout">
      <section className="login-intro">
        <span className="brand-mark" aria-hidden="true">S</span>
        <div className="eyebrow">SMARTIR-NET / SECURITY OPERATIONS</div>
        <h1>
          De los eventos<br />
          a una respuesta<br />
          <em>con trazabilidad.</em>
        </h1>
        <p>
          Correlación, priorización explicable y gestión de incidentes en un
          solo espacio de trabajo.
        </p>
        <div className="login-features">
          <span>01 · Observar</span>
          <span>02 · Priorizar</span>
          <span>03 · Responder</span>
        </div>
        <small>PLATAFORMA ACADÉMICA · ENTORNO AUTORIZADO</small>
      </section>

      <div className="login-form-wrap">
        <section className="panel login-panel">
          <span className="eyebrow">ACCESO A LA PLATAFORMA</span>
          <h2>Iniciar sesión</h2>
          <p>Utilice su cuenta de administrador, analista u observador.</p>
          {message && <Notice>{message}</Notice>}
          {error && <Notice tone="error">{error}</Notice>}

          <form onSubmit={submit}>
            <label>
              Usuario
              <input
                autoComplete="username"
                required
                maxLength={100}
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </label>
            <label>
              Contraseña
              <input
                type="password"
                autoComplete="current-password"
                required
                maxLength={128}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
            <button disabled={busy}>{busy ? 'Verificando…' : 'Entrar'}</button>
          </form>

          <div className="login-security">
            Sesión de 15 minutos · Validación de identidad con la API.
            <p>
              Las credenciales y tokens no se guardan en el almacenamiento de
              JavaScript.
            </p>
          </div>
        </section>
      </div>
    </div>
  );
}
