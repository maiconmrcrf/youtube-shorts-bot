let iaAtiva = 'gemini';

const input = document.getElementById('msg-input');
const btn = document.getElementById('btn-enviar');
const chat = document.getElementById('chat-mensagens');

input.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') enviarMensagem();
});

function trocarAba(ia) {
    iaAtiva = ia;
    document.querySelectorAll('.aba').forEach(b => {
        b.classList.toggle('ativa', b.dataset.ia === ia);
    });
}

async function carregarHistorico() {
    try {
        const resp = await fetch('/historico');
        const lista = await resp.json();
        chat.innerHTML = '';

        if (!lista.length) {
            adicionarMsg('ia', 'Oi! Sou sua IA pessoal. Como posso ajudar?', false, 'Gemini');
            return;
        }

        lista.forEach(item => {
            adicionarMsg('user', item.user);
            adicionarMsg('ia', item.ia, false, item.quem, item.tipo, item.midia);
        });
    } catch (e) {
        console.error(e);
    }
}

async function enviarMensagem() {
    const msg = input.value.trim();
    if (!msg) return;

    adicionarMsg('user', msg);
    input.value = '';
    btn.disabled = true;

    const digitando = adicionarMsg('ia', '⏳ Pensando...', true);

    try {
        const resp = await fetch('/chat', {
            method: 'POST',
            headers: {'Content-Type': 'application/x-www-form-urlencoded'},
            body: 'msg=' + encodeURIComponent(msg) + '&ia=' + encodeURIComponent(iaAtiva)
        });
        const dados = await resp.json();

        digitando.remove();

        if (dados.erro) {
            adicionarMsg('ia', '❌ Erro: ' + dados.erro);
        } else {
            adicionarMsg('ia', dados.resposta, false, dados.ia, dados.tipo, dados.midia);
        }
    } catch (e) {
        digitando.remove();
        adicionarMsg('ia', '❌ Erro de conexão: ' + e.message);
    }

    btn.disabled = false;
    input.focus();
}

function adicionarMsg(tipo, texto, temporario = false, ia = null, tipoMidia = null, midia = null) {
    const div = document.createElement('div');
    div.className = 'msg-' + tipo;
    if (temporario) div.classList.add('temporario');

    const balao = document.createElement('div');
    balao.className = 'balao';

    if (ia) {
        const tag = document.createElement('span');
        tag.className = 'tag-ia';
        tag.textContent = '[' + ia + ']';
        balao.appendChild(tag);
    }

    // Texto
    const span = document.createElement('span');
    span.innerHTML = texto.replace(/\n/g, '<br>');
    balao.appendChild(span);

    // Midia (imagem ou video)
    if (midia) {
        const divMidia = document.createElement('div');
        divMidia.style.marginTop = '10px';

        if (tipoMidia === 'imagem') {
            const img = document.createElement('img');
            img.src = '/midia/' + midia;
            img.style.maxWidth = '100%';
            img.style.borderRadius = '10px';
            img.style.cursor = 'pointer';
            img.onclick = () => window.open('/midia/' + midia, '_blank');
            divMidia.appendChild(img);
        } else if (tipoMidia === 'video') {
            const vid = document.createElement('video');
            vid.src = '/midia/' + midia;
            vid.controls = true;
            vid.style.maxWidth = '100%';
            vid.style.borderRadius = '10px';
            divMidia.appendChild(vid);
        }

        balao.appendChild(divMidia);
    }

    div.appendChild(balao);
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
    return div;
}

async function limparChat() {
    if (!confirm('Limpar toda a conversa?')) return;
    await fetch('/limpar', {method: 'POST'});
    carregarHistorico();
}

carregarHistorico();
