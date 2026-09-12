import React from 'react';

/**
 * Global Error Boundary - previne "tela branca" quando um componente React lança.
 * Escopo intencionalmente mínimo. Não faz refactor, apenas um fallback seguro.
 */
class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    // Log para console; observabilidade real fica para tarefa futura
    console.error('[ErrorBoundary]', error, errorInfo);
  }

  handleReload = () => {
    // Limpa cache de service worker se possível e recarrega
    try {
      if ('caches' in window) {
        caches.keys().then((keys) => keys.forEach((k) => caches.delete(k)));
      }
    } catch (_) {}
    window.location.reload();
  };

  handleGoLogin = () => {
    try {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
    } catch (_) {}
    window.location.href = '/login';
  };

  render() {
    if (this.state.hasError) {
      return (
        <div
          data-testid="error-boundary-fallback"
          style={{
            minHeight: '100vh',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '24px',
            background: '#faf7f0',
            fontFamily: 'system-ui, -apple-system, sans-serif',
          }}
        >
          <div style={{ maxWidth: 480, textAlign: 'center' }}>
            <h1 style={{ fontSize: 28, marginBottom: 12, color: '#7a1f1f' }}>
              Algo deu errado
            </h1>
            <p style={{ color: '#555', marginBottom: 24 }}>
              Ocorreu um erro inesperado ao carregar a tela. Nenhum dado foi perdido.
              Você pode recarregar a página ou voltar para o login.
            </p>
            <div style={{ display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap' }}>
              <button
                data-testid="error-boundary-reload-btn"
                onClick={this.handleReload}
                style={{
                  padding: '10px 20px',
                  background: '#7a1f1f',
                  color: '#fff',
                  border: 'none',
                  borderRadius: 6,
                  cursor: 'pointer',
                  fontSize: 15,
                }}
              >
                Recarregar
              </button>
              <button
                data-testid="error-boundary-login-btn"
                onClick={this.handleGoLogin}
                style={{
                  padding: '10px 20px',
                  background: 'transparent',
                  color: '#7a1f1f',
                  border: '1px solid #7a1f1f',
                  borderRadius: 6,
                  cursor: 'pointer',
                  fontSize: 15,
                }}
              >
                Ir para Login
              </button>
            </div>
            {this.state.error && (
              <details style={{ marginTop: 24, textAlign: 'left', color: '#888', fontSize: 12 }}>
                <summary style={{ cursor: 'pointer' }}>Detalhes técnicos</summary>
                <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', marginTop: 8 }}>
                  {String(this.state.error?.message || this.state.error)}
                </pre>
              </details>
            )}
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

export default ErrorBoundary;
