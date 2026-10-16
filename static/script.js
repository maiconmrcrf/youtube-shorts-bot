// Mostrar/ocultar agendamento
document.querySelectorAll('input[name="modo"]').forEach(radio => {
    radio.addEventListener('change', (e) => {
        const ag = document.getElementById('agendamento');
        if (e.target.value === 'agendar') {
            ag.classList.remove('escondido');
        } else {
            ag.classList.add('escondido');
        }
    });
});

async function criarVideo() {
    const url = document.getElementById('url_baixo').value.trim();
    if (!url) {
        alert('Cola o link do vídeo primeiro!');
        return;
    }

    const btn = document.getElementById('btn-criar');
    btn.disabled = true;
    btn.textContent = '⏳ Criando...';

    document.getElementById('progresso').classList.remove('escondido');
    document.getElementById('resultado').classList.add('escondido');

    try {
        const resp = await fetch('/criar', {
            method: 'POST',
            headers: {'Content-Type': 'application/x-www-form-urlencoded'},
            body: 'url_baixo=' + encodeURIComponent(url)
        });
        const dados = await resp.json();

        if (dados.erro) {
            alert('Erro: ' + dados.erro);
            btn.disabled = false;
            btn.textContent = '✨ CRIAR VÍDEO';
            return;
        }

        acompanharStatus(dados.job_id);

    } catch (e) {
        alert('Erro de conexão: ' + e.message);
        btn.disabled = false;
        btn.textContent = '✨ CRIAR VÍDEO';
    }
}

async function acompanharStatus(jobId) {
    const interval = setInterval(async () => {
        try {
            const resp = await fetch('/status/' + jobId);
            const dados = await resp.json();

            document.getElementById('barra').style.width = dados.progresso + '%';
            document.getElementById('msg-progresso').textContent = dados.msg;

            if (dados.status === 'concluido') {
                clearInterval(interval);
                document.getElementById('resultado').classList.remove('escondido');
                document.getElementById('res-titulo').textContent = dados.titulo || '—';
                document.getElementById('res-frase').textContent = dados.frase || '—';
                document.getElementById('res-video').textContent = dados.video || '—';

                const btn = document.getElementById('btn-criar');
                btn.disabled = false;
                btn.textContent = '✨ CRIAR VÍDEO';
            } else if (dados.status === 'erro') {
                clearInterval(interval);
                alert('Erro: ' + dados.msg);
                const btn = document.getElementById('btn-criar');
                btn.disabled = false;
                btn.textContent = '✨ CRIAR VÍDEO';
            }
        } catch (e) {
            console.error('Erro ao checar status:', e);
        }
    }, 1500);
}
