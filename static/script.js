let iaAtiva = 'gemini';

const input = document.getElementById('msg-input');
const btn = document.getElementById('btn-enviar');
const chat = document.getElementById('chat-mensagens');

input.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') enviarMensagem();
});

// Troca de aba
function trocarAba(ia) {
    iaAtiva = ia;

    // Atualiza botões
    document.querySelectorAll('.aba').forEach(b => {
        b.classList.toggle('ativa', b.dataset.ia === ia);
    });

    // Carrega histórico da IA
    carregarHistorico();
}

// Carrega histórico da IA ativa
async function carregarHistorico() {
    chat.innerHTML = '';

    try {
        const resp = await fetch('/historico/' + iaAtiva);
        const lista = await resp.json();

        if (!lista.length) {
            const nome = iaAtiva === 'gemini' ? 'Gemini' : 'Groq';
            adicionarMsg('ia', `Oi! Sou o ${nome}. Como posso ajudar?`);
            return;
        }

        lista.forEach(item => {
            adicionarMsg('user', item.user);
            adicionarMsg('ia', item.ia);
        });
    } catch (e) {
        adicionarMsg('ia', '❌ Erro ao carregar histórico');
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
            adicionarMsg('ia', dados.resposta, false, dados.ia);
        }
    } catch (e) {
        digitando.remove();
        adicionarMsg('ia', '❌ Erro de conexão: ' + e.message);
    }

    btn.disabled = false;
    input.focus();
}

function adicionarMsg(tipo, texto, temporario = false, ia = null) {
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

    const span = document.createElement('span');
    span.innerHTML = texto.replace(/\n/g, '<br>');
    balao.appendChild(span);

    div.appendChild(balao);
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;

    return div;
}

async function limparChat() {
    if (!confirm('Limpar a conversa do ' + (iaAtiva === 'gemini' ? 'Gemini' : 'Groq') + '?')) return;
    await fetch('/limpar/' + iaAtiva, {method: 'POST'});
    carregarHistorico();
}

// Inicia
carregarHistorico();
