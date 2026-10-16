const input = document.getElementById('msg-input');
const btn = document.getElementById('btn-enviar');
const chat = document.getElementById('chat-mensagens');

input.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') enviarMensagem();
});

async function enviarMensagem() {
    const msg = input.value.trim();
    if (!msg) return;

    // Adiciona mensagem do usuário
    adicionarMsg('user', msg);
    input.value = '';
    btn.disabled = true;

    // Adiciona "digitando..."
    const digitando = adicionarMsg('ia', '⏳ Pensando...', true);

    try {
        const resp = await fetch('/chat', {
            method: 'POST',
            headers: {'Content-Type': 'application/x-www-form-urlencoded'},
            body: 'msg=' + encodeURIComponent(msg)
        });
        const dados = await resp.json();

        // Remove o "digitando..."
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

    // Nome da IA (se tiver)
    if (ia) {
        const tag = document.createElement('span');
        tag.className = 'tag-ia';
        tag.textContent = '[' + ia + ']';
        balao.appendChild(tag);
    }

    // Texto com quebras de linha
    const span = document.createElement('span');
    span.innerHTML = texto.replace(/\\n/g, '<br>');
    balao.appendChild(span);

    div.appendChild(balao);
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;

    return div;
}

async function limparChat() {
    if (!confirm('Limpar toda a conversa?')) return;
    await fetch('/limpar', {method: 'POST'});
    chat.innerHTML = '<div class="msg-ia"><div class="balao">Oi! Sou sua IA pessoal. Como posso ajudar?</div></div>';
}
