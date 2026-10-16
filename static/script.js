let jobAtual = null;

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

        jobAtual = dados.job_id;
        acompanharStatus(jobAtual);

    } catch (e) {
        alert('Erro: ' + e.message);
        btn.disabled = false;
        btn.textContent = '✨ CRIAR VÍDEO';
    }
}

async function acompanharStatus(jobId) {
    const interval = setInterval(async () => {
        try {
            const resp = await fetch('/status/' + jobId);
            const dados = await resp.json();

            document.getElementById('barra').style.width = (dados.progresso || 0) + '%';
            document.getElementById('msg-progresso').textContent = dados.msg || '';

            if (dados.status === 'concluido') {
                clearInterval(interval);
                mostrarResultado(dados);
                document.getElementById('btn-criar').disabled = false;
                document.getElementById('btn-criar').textContent = '✨ CRIAR VÍDEO';
            } else if (dados.status === 'erro') {
                clearInterval(interval);
                alert('Erro: ' + dados.msg);
                document.getElementById('btn-criar').disabled = false;
                document.getElementById('btn-criar').textContent = '✨ CRIAR VÍDEO';
            }
        } catch (e) {
            console.error(e);
        }
    }, 2000);
}

function mostrarResultado(dados) {
    document.getElementById('resultado').classList.remove('escondido');
    document.getElementById('res-titulo').textContent = dados.titulo || '—';
    document.getElementById('res-descricao').textContent = dados.descricao || '—';
    document.getElementById('res-tags').textContent = (dados.tags || []).join(', ') || '—';
    document.getElementById('res-hashtags').textContent = dados.hashtags || '—';
    document.getElementById('res-frase').textContent = dados.frase || '—';

    // Vídeo
    const videoEl = document.getElementById('res-video');
    if (dados.video) {
        const nome = dados.video.split('/').pop();
        videoEl.src = '/video/' + nome;
        videoEl.load();
    }

    // Mostra botões de ação
    document.getElementById('acoes').classList.remove('escondido');
    document.getElementById('agendamento-box').classList.add('escondido');
}

async function postarVideo() {
    if (!jobAtual) return;

    const btn = event.target;
    btn.disabled = true;
    btn.textContent = '⏳ Postando...';

    try {
        const resp = await fetch('/postar/' + jobAtual, {method: 'POST'});
        const dados = await resp.json();

        // Acompanha
        const interval = setInterval(async () => {
            const r = await fetch('/status/' + jobAtual);
            const d = await r.json();

            if (d.status === 'postado') {
                clearInterval(interval);
                alert('✅ Postado com sucesso!');
                document.getElementById('acoes').classList.add('escondido');
                carregarHistorico();
            } else if (d.status === 'limite') {
                clearInterval(interval);
                // Mostra agendamento
                document.getElementById('acoes').classList.add('escondido');
                document.getElementById('agendamento-box').classList.remove('escondido');
            } else if (d.status === 'erro') {
                clearInterval(interval);
                alert('Erro: ' + d.msg);
                btn.disabled = false;
                btn.textContent = '✅ SIM, POSTAR AGORA';
            }
        }, 2000);

    } catch (e) {
        alert('Erro: ' + e.message);
        btn.disabled = false;
        btn.textContent = '✅ SIM, POSTAR AGORA';
    }
}

function naoPostar() {
    document.getElementById('acoes').classList.add('escondido');
    document.getElementById('agendamento-box').classList.remove('escondido');
}

async function agendarVideo() {
    const data = document.getElementById('data_agendamento').value;
    if (!data) {
        alert('Escolhe a data e hora!');
        return;
    }

    try {
        const resp = await fetch('/agendar/' + jobAtual, {
            method: 'POST',
            headers: {'Content-Type': 'application/x-www-form-urlencoded'},
            body: 'data_hora=' + encodeURIComponent(data)
        });
        const dados = await resp.json();
        if (dados.ok) {
            alert('✅ Agendado pra ' + data);
            document.getElementById('agendamento-box').classList.add('escondido');
            carregarHistorico();
        } else {
            alert('Erro: ' + dados.erro);
        }
    } catch (e) {
        alert('Erro: ' + e.message);
    }
}

async function carregarHistorico() {
    try {
        const resp = await fetch('/historico');
        const lista = await resp.json();
        const div = document.getElementById('historico-lista');

        if (!lista.length) {
            div.innerHTML = '<p class="vazio">Nenhum vídeo criado ainda.</p>';
            return;
        }

        div.innerHTML = lista.reverse().map(item => `
            <div class="item-historico">
                <div class="item-header">
                    <span class="status-dot ${item.status}"></span>
                    <strong>${item.titulo || 'Sem título'}</strong>
                    <small>${item.data}</small>
                </div>
                <p class="item-desc">${item.descricao || ''}</p>
                <p class="item-tags">${(item.tags || []).join(', ')}</p>
                <p class="item-hashtags">${item.hashtags || ''}</p>
                <p class="item-frase">💬 ${item.frase || ''}</p>
                ${item.video ? `<video controls width="100%" src="/video/${item.video.split('/').pop()}" style="border-radius: 8px; margin-top: 8px;"></video>` : ''}
                <span class="item-status">${item.status}</span>
            </div>
        `).join('');
    } catch (e) {
        console.error(e);
    }
}

// Carrega histórico ao abrir
carregarHistorico();
setInterval(carregarHistorico, 10000);
