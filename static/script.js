let iaAtiva = 'gemini';

const input = document.getElementById('msg-input');
const btn = document.getElementById('btn-enviar');
const chat = document.getElementById('chat-mensagens');

input.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') enviarMensagem();
});

// Troca de aba (NÃO recarrega histórico, só muda a cor)
function trocarAba(ia) {
    iaAtiva = ia;
    document.querySelectorAll('.aba').forEach(b => {
        b.classList.toggle('ativa', b.dataset.ia === ia);
    });
    // Foca no input pra continuar digitando
    input.focus();
}

// Carrega histórico do servidor (uma vez só, no início)
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
            adicionarMsg('ia', item.ia, false, item.quem || 'IA');
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
    if (!confirm('Limpar toda a conversa?')) return;
    await fetch('/limpar', {method: 'POST'});
    carregarHistorico();
}

// Inicia
carregarHistorico();
