using System.Collections;
using TMPro;
using UniVRM10;
using UnityEngine;
using UnityEngine.UI;

/// <summary>
/// Controla a mão que aparece durante a ação ALLOWPET. A mão NÃO segue
/// a posição do mouse — arrastar pra esquerda/direita gira a mão ao
/// longo de um arco fixo acima da cabeça (como girar um mostrador), em
/// vez de tentar casar a posição da mão com a posição do cursor no
/// mundo.
///
/// Isso simplifica bastante a colisão: como o raio do arco (distância
/// até o centro da cabeça) é sempre o mesmo — a distância original até
/// pontoAncoragem — girar em torno desse raio NUNCA entra na cabeça,
/// contanto que o ponto de ancoragem já esteja posicionado fora dela.
/// Não precisa de ComputePenetration nem de nenhuma lógica de
/// colisão em tempo real.
///
/// A sessão agora tem um critério de término real: uma barra de
/// progresso (pet_bar) enche conforme a mão se movimenta; ao encher
/// por completo, um texto flutuante (ex: um coração) sobe e some na
/// cabeça, e a sessão é encerrada.
///
/// A sessão também tem um CRONÔMETRO: o tempo entre Iniciar() e a
/// conclusão (ou o timeout) é reportado de volta ao backend Python via
/// VenusRequester.Ask(), como uma mensagem de sistema — igual a um
/// poke. Se o usuário completar a barra dentro de tempoLimiteSegundos,
/// Gemini recebe quanto tempo levou; se o tempo limite estourar antes
/// da conclusão, Gemini recebe um aviso de que o usuário não fez o
/// carinho. Em ambos os casos a resposta chega depois, normalmente,
/// via ResponseListener — este script não espera por ela.
///
/// [DEBUG BUILD] Three temporary Debug.Log calls added (Start(),
/// Iniciar(), Encerrar()) to trace an issue where the hand stays
/// active/visible even though nothing in the normal code path should
/// be calling Iniciar(). Remove all three once the cause is found —
/// search for "[DEBUG]" to find them.
/// </summary>
[RequireComponent(typeof(Collider))]
public class AllowPetController : MonoBehaviour
{
    [Header("Referências")]
    [Tooltip("Ponto de ancoragem: define o RAIO do arco (distância até o centro da cabeça) e a direção de repouso ('topo') a partir da qual o arco é medido.")]
    public Transform pontoAncoragem;

    [Tooltip("Collider da cabeça — usado só pra saber o centro em torno do qual o arco gira.")]
    public SphereCollider colisorCabeca;

    [Tooltip("Osso da cabeça — precisa ter um PokeSpring pra reagir ao movimento da mão")]
    public Transform ossoCabeca;

    [Header("Arco (esquerda/direita)")]
    [Tooltip("Ângulo máximo, em graus, que a mão pode girar pra cada lado a partir da posição de repouso (pontoAncoragem).")]
    public float anguloMaximoArco = 45f;

    [Tooltip("Graus de giro por pixel de movimento horizontal do mouse. Inverta o sinal (valor negativo) se a direção do giro estiver invertida.")]
    public float sensibilidadeArrasto = 0.2f;

    [Header("Reação do osso")]
    [Tooltip("Quanto o deslocamento da mão (em unidades de mundo por frame) vira força de impulso na PokeSpring")]
    public float sensibilidadeImpulso = 40f;

    [Tooltip("Impulso máximo aplicado em um único frame, pra evitar puxões absurdos em arrastos muito rápidos")]
    public float impulsoMaximo = 25f;

    [Header("Inclinação da cabeça durante o carinho")]
    [Tooltip("Força do impulso contínuo que inclina a cabeça levemente pra frente enquanto a mão está de fato em movimento (arrastando). Zero desativa.")]
    public float forcaInclinacaoFrente = 3f;

    [Tooltip("Eixo LOCAL do osso da cabeça usado como eixo de rotação da inclinação pra frente (tipicamente o eixo lateral do osso, pra fazer a cabeça 'balançar' pra baixo/frente).")]
    public Vector3 eixoInclinacaoFrenteLocal = Vector3.right;

    [Header("Inclinação da mão perto do limite do arco")]
    [Tooltip("Ângulo máximo (graus) que a mão inclina (roll) ao se aproximar do limite do arco. Zero desativa.")]
    public float inclinacaoMaximaMao = 15f;

    [Tooltip("Expoente da curva de inclinação: 1 = inclina de forma linear conforme anguloAtual cresce; valores >1 fazem a inclinação só aparecer perceptivelmente perto do limite.")]
    public float curvaInclinacaoMao = 2f;

    [Header("Integração com outros sistemas durante o arrasto")]
    [Tooltip("Script de IK que faz a cabeça seguir o mouse. É desativado (ForcarTracking(false)) enquanto a mão está sendo arrastada, pra não competir com o impulso físico da PokeSpring, e devolvido ao comportamento natural quando o arrasto termina.")]
    public HeadFollowMouseIK headFollowMouseIK;

    [Tooltip("Script de piscar automático. É desativado (enabled = false) enquanto a mão está sendo arrastada, pra não competir com o fechamento forçado dos olhos — os dois escrevem no mesmo ExpressionKey.Blink do VRM, então deixá-lo ligado causaria flicker entre 'olhos fechados pelo carinho' e o próximo piscar aleatório.")]
    public AutoBlink autoBlink;

    [Tooltip("GameObject do canvas de arrastar a JANELA (pacote de terceiros, ex: DragMoveCanvas/WindowMoveHandle). É desativado (SetActive(false)) durante toda a sessão de carinho — desde Iniciar() até Encerrar() — pra não competir com o arrasto da mão: os dois reagem ao mesmo clique/arrasto do mouse, então sem isso, mover a mão também arrasta a janela inteira. Desativar já em Iniciar() (em vez de só em IniciarArrasto) evita depender da ordem de execução entre este script e o EventSystem no mesmo frame do clique.")]
    public GameObject dragMoveCanvas;

    [Tooltip("Referência ao Vrm10Instance do modelo (mesmo GameObject ou pai) — usado pra fechar os olhos via VRM10 Expression (ExpressionKey.Blink) enquanto a mão está sendo arrastada, em vez de escrever direto num blend shape via SkinnedMeshRenderer.")]
    public Vrm10Instance vrm10Instance;

    [Tooltip("Velocidade de fechamento/abertura dos olhos, em peso de expression VRM (0-1) por segundo.")]
    public float velocidadeFechamentoOlhos = 4f;

    [Tooltip("AudioSource usado pra tocar o som de carinho em loop enquanto a mão está sendo arrastada. O clip deve estar atribuído no próprio AudioSource; o loop é forçado via código. A fonte toca continuamente durante o arrasto — a audibilidade é controlada por fade de volume, não por Pause()/Play(), pra evitar cliques.")]
    public AudioSource fonteSomCarinho;

    [Tooltip("Volume máximo (0-1) do som de carinho quando a mão está se movendo.")]
    public float volumeMaximoSomCarinho = 1f;

    [Tooltip("Velocidade do fade de volume (0-1 por segundo) ao começar ou parar de mover a mão. Valores baixos = fade mais suave e lento; valores altos = quase instantâneo.")]
    public float velocidadeFadeSomCarinho = 6f;

    [Header("Barra de progresso (pet_bar)")]
    [Tooltip("Image SÓLIDA (Type = Filled) usada como o preenchimento da barra — fica ATRÁS da moldura decorativa (pet_bar), preenchendo por baixo dela pra criar a ilusão de uma barra enchendo. NÃO é o pet_bar em si.")]
    public Image barraCarinho;

    [Tooltip("GameObject pai que agrupa a moldura decorativa (pet_bar) e o preenchimento sólido (barraCarinho). Controla show/hide dos dois juntos. Se vazio, cai de volta pra só mostrar/esconder o GameObject do próprio barraCarinho.")]
    public GameObject containerBarraCarinho;

    [Tooltip("Soma total de graus de movimento do arco (valor absoluto — ida e volta contam igual) necessária pra encher a barra por completo.")]
    public float distanciaAngularParaCompletar = 720f;

    [Header("Conclusão")]
    [Tooltip("Texto/símbolo mostrado quando a barra enche por completo (ex: um coração '❤'). Sobe e desaparece, no mesmo estilo do MoodChangeIndicator — bem mais leve que um ParticleSystem.")]
    public string textoEfeitoConclusao = "❤";

    [Tooltip("Onde o texto de conclusão aparece. Se vazio, usa o centro do colisorCabeca.")]
    public Transform pontoEfeitoConclusao;

    [Tooltip("Fonte TMP usada no texto de conclusão. Se vazio, usa a fonte padrão do TextMeshPro.")]
    public TMP_FontAsset fonteEfeitoConclusao;

    [Tooltip("Cor do texto de conclusão.")]
    public Color corEfeitoConclusao = new Color(1f, 0.4f, 0.7f);

    [Tooltip("Tamanho da fonte do texto de conclusão.")]
    public float tamanhoFonteEfeitoConclusao = 3f;

    [Tooltip("Distância (em unidades de mundo) que o texto sobe antes de desaparecer.")]
    public float distanciaSubidaEfeitoConclusao = 0.5f;

    [Tooltip("Duração total da animação de subida/desaparecimento, em segundos.")]
    public float duracaoEfeitoConclusao = 1.5f;

    [Header("Cronômetro (relatado ao Gemini)")]
    [Tooltip("Tempo máximo, em segundos, que o usuário tem — a partir de Iniciar() — pra completar o carinho antes de a sessão expirar. Se estourar sem conclusão, um aviso de timeout é enviado ao backend e a sessão é encerrada.")]
    public float tempoLimiteSegundos = 180f; // 3 minutos

    [Header("Resposta do Python")]
    [Tooltip("ResponseListener que recebe as respostas do backend Python. Se vazio, tenta achar um na cena.")]
    public ResponseListener responseListener;

    private PokeSpring springCabeca;
    private Camera cameraPrincipal;
    private bool arrastando = false;
    private Vector3 posicaoAnterior;
    private float ultimoMouseX;
    private float anguloAtual = 0f;
    private float raioArco;
    private Vector3 direcaoRepousoBase; // direção do centro da cabeça até pontoAncoragem, no momento em que a sessão começou
    private Quaternion rotacaoBaseMao;  // rotação de repouso da mão, capturada no início da sessão, usada como base pra inclinação

    private float pesoOlhoAtual = 0f;
    private float pesoOlhoDesejado = 0f;

    private float volumeSomAtual = 0f;
    private float volumeSomDesejado = 0f;

    private float progressoAcumulado = 0f;
    private bool concluido = false;

    // Marca o Time.time em que a sessão atual começou (definido em
    // Iniciar(), só quando a sessão de fato reinicia — ver comentário
    // lá). Usado tanto pra calcular quanto tempo levou até concluir
    // quanto pra saber se tempoLimiteSegundos já estourou.
    private float tempoInicioSessao = 0f;



    void Awake()
    {
        cameraPrincipal = Camera.main;

        if (ossoCabeca != null)
        {
            springCabeca = ossoCabeca.GetComponent<PokeSpring>();

            if (springCabeca == null)
            {
                Debug.LogWarning("AllowPetController: ossoCabeca não tem um componente PokeSpring — a cabeça não vai reagir ao carinho.");
            }
        }

        if (vrm10Instance == null)
        {
            vrm10Instance = GetComponent<Vrm10Instance>();

            if (vrm10Instance == null)
            {
                vrm10Instance = GetComponentInParent<Vrm10Instance>();
            }
        }

        if (vrm10Instance == null)
        {
            Debug.LogWarning("AllowPetController: Vrm10Instance não encontrado — os olhos não vão fechar durante o carinho.");
        }

        if (fonteSomCarinho != null)
        {
            fonteSomCarinho.loop = true;

            if (fonteSomCarinho.clip == null)
            {
                Debug.LogWarning("AllowPetController: fonteSomCarinho não tem nenhum AudioClip atribuído — não vai tocar nada durante o carinho.");
            }
        }
    }

    void Start()
    {
        if (responseListener == null)
        {
            responseListener = FindFirstObjectByType<ResponseListener>();
        }

        // A inscrição é feita AQUI, em Start() — não em OnEnable/OnDisable
        // — pelo MESMO motivo documentado em SpeechBubble.cs: este script
        // desativa o próprio gameObject repetidamente (Iniciar() ativa,
        // Encerrar() desativa) como parte do ciclo normal de uma sessão
        // de carinho. Se a inscrição estivesse em OnEnable/OnDisable, o
        // Encerrar() de UMA sessão desinscreveria o script antes da
        // PRÓXIMA ação ALLOWPET chegar — e como é justamente esse evento
        // que chama Iniciar() pra reativar a mão, ela nunca mais
        // receberia a próxima resposta (deadlock: precisa estar
        // inscrito pra reativar, mas só reativa quando inscrito).
        if (responseListener != null)
        {
            responseListener.OnResponseReceived += HandleResponseReceived;
        }
        else
        {
            Debug.LogWarning("AllowPetController: nenhum ResponseListener encontrado — não vai reagir a ALLOWPET.");
        }

        // A mão começa escondida — mas SÓ depois de já estar inscrita
        // acima. Diferente do padrão documentado como "Awake()
        // self-deactivation trap" (desativar via Inspector em vez de
        // código), aqui o gameObject PRECISA começar ativo no Inspector
        // pra Start() rodar; é o SetActive(false) em CÓDIGO, executado
        // depois da inscrição, que garante o estado inicial escondido.
        gameObject.SetActive(false);

        Debug.Log($"[AllowPetController][DEBUG] Start() finished. activeSelf={gameObject.activeSelf}");
    }

    void OnDestroy()
    {
        if (responseListener != null)
        {
            responseListener.OnResponseReceived -= HandleResponseReceived;
        }
    }

    /// <summary>
    /// Chamado sempre que o Python devolve uma resposta. Só reage
    /// quando action == "ALLOWPET" — qualquer outra resposta é
    /// ignorada aqui (outros scripts cuidam das outras ações).
    /// </summary>
    private void HandleResponseReceived(VenusResponse resposta)
    {
        if (resposta == null) return;
        if (resposta.action != "ALLOWPET") return;

        Iniciar();
    }

    /// <summary>
    /// Chamado ao receber uma resposta com action == "ALLOWPET" (ver
    /// HandleResponseReceived acima). Recalcula o raio/direção de
    /// repouso do arco, zera o ângulo, o progresso da barra e o
    /// cronômetro da sessão, e torna a mão (e a barra) visíveis/
    /// clicáveis. Chamar de novo enquanto já está em arrasto não reseta
    /// nada (evita "puxar" a mão do usuário ou reiniciar o cronômetro
    /// no meio de uma interação).
    /// </summary>
    public void Iniciar()
    {
        Debug.Log("[AllowPetController][DEBUG] Iniciar() called. Click the log entry above to expand its call stack and see who called it.");

        if (pontoAncoragem == null || colisorCabeca == null)
        {
            Debug.LogWarning("AllowPetController: pontoAncoragem ou colisorCabeca não foram definidos no Inspector.");
            return;
        }

        if (!arrastando)
        {
            Vector3 centroCabeca = colisorCabeca.bounds.center;
            Vector3 offset = pontoAncoragem.position - centroCabeca;

            raioArco = offset.magnitude;
            direcaoRepousoBase = raioArco > 0.0001f ? offset.normalized : Vector3.up;
            anguloAtual = 0f;

            transform.position = pontoAncoragem.position;
            rotacaoBaseMao = transform.rotation;

            progressoAcumulado = 0f;
            concluido = false;

            // Cronômetro da sessão começa agora — usado tanto pra medir
            // quanto tempo o carinho levou (NotificarConcluido) quanto
            // pra detectar o timeout (VerificarTimeout).
            tempoInicioSessao = Time.time;

            if (barraCarinho != null)
            {
                barraCarinho.fillAmount = 0f;

                if (containerBarraCarinho != null)
                {
                    containerBarraCarinho.SetActive(true);
                }
                else
                {
                    barraCarinho.gameObject.SetActive(true);
                }
            }
        }

        gameObject.SetActive(true);

        if (dragMoveCanvas != null)
        {
            dragMoveCanvas.SetActive(false);
        }

        if (cameraPrincipal == null) cameraPrincipal = Camera.main;
    }

    /// <summary>
    /// Esconde a mão e a barra, e encerra a sessão de carinho. Chamado
    /// automaticamente ao completar a barra ou ao estourar o tempo
    /// limite, ou manualmente se algum dia for necessário. Não envia
    /// nada ao backend por conta própria — isso é responsabilidade de
    /// quem chama Encerrar() (ConcluirCarinho ou VerificarTimeout), já
    /// que só eles sabem POR QUE a sessão está terminando.
    /// </summary>
    public void Encerrar()
    {
        Debug.Log("[AllowPetController][DEBUG] Encerrar() called. Click the log entry above to expand its call stack and see who called it.");

        // Garante que o head-follow, o autoBlink, o som e o estado de
        // arrasto voltem ao normal mesmo se Encerrar() for chamado no
        // meio de um arrasto.
        PararArrasto();

        // Fecha os olhos de volta instantaneamente (sem interpolação):
        // como o objeto vai ser desativado, o Update() que faria o
        // fechamento suave não vai mais rodar, então uma interpolação
        // aqui deixaria os olhos travados a meio caminho.
        pesoOlhoAtual = 0f;
        if (vrm10Instance != null)
        {
            vrm10Instance.Runtime.Expression.SetWeight(ExpressionKey.Blink, pesoOlhoAtual);
        }

        if (barraCarinho != null)
        {
            barraCarinho.fillAmount = 0f;

            if (containerBarraCarinho != null)
            {
                containerBarraCarinho.SetActive(false);
            }
            else
            {
                barraCarinho.gameObject.SetActive(false);
            }
        }

        gameObject.SetActive(false);

        if (dragMoveCanvas != null)
        {
            dragMoveCanvas.SetActive(true);
        }
    }

    void Update()
    {
        if (!gameObject.activeSelf) return;

        // Checado ANTES de qualquer outra coisa: se o tempo limite já
        // estourou, a sessão é encerrada (e o backend avisado) neste
        // mesmo frame, sem processar arrasto/clique — VerificarTimeout()
        // já chama Encerrar() internamente, o que desativa o
        // gameObject, então nada mais deste método deveria rodar.
        if (VerificarTimeout()) return;

        if (Input.GetMouseButtonDown(0))
        {
            VerificarInicioArrasto();
        }
        else if (Input.GetMouseButtonUp(0))
        {
            PararArrasto();
        }

        if (arrastando)
        {
            AtualizarArrasto();
        }

        AtualizarFechamentoOlhos();
    }

    /// <summary>
    /// Retorna true (e já encerra a sessão, avisando o backend) se
    /// tempoLimiteSegundos se passaram desde tempoInicioSessao sem que
    /// concluido tenha se tornado true. Não faz nada se a sessão já foi
    /// concluída — o carinho completo tem prioridade sobre o timeout,
    /// mesmo que os dois caiam no mesmo frame.
    /// </summary>
    private bool VerificarTimeout()
    {
        if (concluido) return false;
        if (Time.time - tempoInicioSessao < tempoLimiteSegundos) return false;

        Debug.Log("[AllowPetController] Tempo limite do carinho estourou sem conclusão — avisando o backend e encerrando.");

        NotificarNaoConcluido();
        Encerrar();

        return true;
    }

    private void VerificarInicioArrasto()
    {
        if (cameraPrincipal == null) return;

        Ray ray = cameraPrincipal.ScreenPointToRay(Input.mousePosition);

        if (Physics.Raycast(ray, out RaycastHit hit, Mathf.Infinity, ~0, QueryTriggerInteraction.Ignore)
            && hit.collider != null && hit.collider.gameObject == gameObject)
        {
            IniciarArrasto();
        }
    }

    /// <summary>
    /// Centraliza tudo que precisa acontecer no exato momento em que o
    /// arrasto começa: guarda o estado inicial do arco, desativa o
    /// head-follow e o piscar automático (pra não competir com o
    /// impulso físico da mão nem com o fechamento forçado dos olhos), e
    /// começa a tocar o som de carinho em loop. O fechamento dos olhos
    /// é só sinalizado aqui (pesoOlhoDesejado) — quem realmente escreve
    /// na expression do VRM, suavemente, é AtualizarFechamentoOlhos().
    /// </summary>
    private void IniciarArrasto()
    {
        arrastando = true;
        posicaoAnterior = transform.position;
        ultimoMouseX = Input.mousePosition.x;

        if (headFollowMouseIK != null)
        {
            headFollowMouseIK.ForceTracking(false);
        }

        if (autoBlink != null)
        {
            autoBlink.enabled = false;
        }

        pesoOlhoDesejado = 1f;

        if (fonteSomCarinho != null && !fonteSomCarinho.isPlaying)
        {
            volumeSomAtual = 0f;
            volumeSomDesejado = 0f;
            fonteSomCarinho.volume = 0f;
            fonteSomCarinho.Play();
        }
    }

    /// <summary>
    /// Centraliza tudo que precisa acontecer quando o arrasto termina
    /// (solta o botão do mouse, ou a sessão é encerrada no meio de um
    /// arrasto): devolve o head-follow e o piscar automático pro
    /// comportamento natural, avisa que os olhos devem abrir de novo, e
    /// para o som de carinho.
    /// </summary>
    private void PararArrasto()
    {
        arrastando = false;

        if (headFollowMouseIK != null)
        {
            headFollowMouseIK.ResumeNaturalBehavior();
        }

        if (autoBlink != null)
        {
            autoBlink.enabled = true;
        }

        pesoOlhoDesejado = 0f;

        if (fonteSomCarinho != null)
        {
            fonteSomCarinho.Stop();
            volumeSomAtual = 0f;
            volumeSomDesejado = 0f;
        }
    }

    /// <summary>
    /// NÃO calcula a posição da mão a partir de onde o mouse está no
    /// mundo. Em vez disso, usa só o quanto o mouse se moveu na
    /// horizontal desde o último frame (delta em pixels) pra girar
    /// anguloAtual — como girar um mostrador. A posição final é sempre
    /// lida de volta do arco fixo, nunca definida diretamente pelo
    /// cursor. A VARIAÇÃO real do ângulo (depois do clamp) também
    /// alimenta a barra de progresso.
    /// </summary>
    private void AtualizarArrasto()
    {
        if (cameraPrincipal == null || colisorCabeca == null) return;

        float mouseXAtual = Input.mousePosition.x;
        float deltaMouseX = mouseXAtual - ultimoMouseX;
        ultimoMouseX = mouseXAtual;

        float anguloAntes = anguloAtual;
        anguloAtual += deltaMouseX * sensibilidadeArrasto;
        anguloAtual = Mathf.Clamp(anguloAtual, -anguloMaximoArco, anguloMaximoArco);

        // Usa a variação REAL (pós-clamp): continuar arrastando contra o
        // limite do arco não deve encher a barra, já que a mão não está
        // de fato se movendo mais.
        float variacaoAngular = Mathf.Abs(anguloAtual - anguloAntes);

        Vector3 centroCabeca = colisorCabeca.bounds.center;

        // Gira a direção de repouso ao redor do eixo de visão da câmera
        // — ou seja, dentro do plano que o jogador está vendo — pra que
        // "arrastar pra direita" sempre pareça girar pra direita na
        // tela, independente de onde a câmera está posicionada na cena.
        Vector3 eixoRotacao = cameraPrincipal.transform.forward;
        Vector3 direcaoAtual = Quaternion.AngleAxis(anguloAtual, eixoRotacao) * direcaoRepousoBase;

        Vector3 novaPosicao = centroCabeca + direcaoAtual * raioArco;
        Vector3 movimentoMundoNoFrame = novaPosicao - posicaoAnterior;

        // Importante: a checagem de "a mão está se movendo" pro som usa
        // deltaMouseX (entrada crua do mouse), NÃO movimentoMundoNoFrame.
        // A posição mundial da mão depende de centroCabeca, que se mexe
        // um pouco sozinho por causa da animação de idle — mesmo com o
        // mouse parado. Usar esse movimento mundial como gatilho fazia o
        // som pausar/retomar em flicker a cada frame.
        bool maoEstaMovendo = Mathf.Abs(deltaMouseX) > 0.01f;

        AplicarImpulsoNaCabeca(movimentoMundoNoFrame);
        AtualizarSomCarinho(maoEstaMovendo);

        transform.position = novaPosicao;
        posicaoAnterior = novaPosicao;

        AtualizarInclinacaoMao();

        // Por último de propósito: pode encerrar a sessão (desativa o
        // GameObject), então nada depois disso deve mexer no estado.
        AcumularProgresso(variacaoAngular);
    }

    /// <summary>
    /// Soma a variação angular deste frame ao progresso acumulado e
    /// atualiza a barra. Ao atingir distanciaAngularParaCompletar,
    /// dispara a conclusão (partículas + aviso ao backend + Encerrar())
    /// uma única vez.
    /// </summary>
    private void AcumularProgresso(float variacaoAngular)
    {
        if (concluido || barraCarinho == null || distanciaAngularParaCompletar <= 0f) return;

        progressoAcumulado += variacaoAngular;
        barraCarinho.fillAmount = Mathf.Clamp01(progressoAcumulado / distanciaAngularParaCompletar);

        if (progressoAcumulado >= distanciaAngularParaCompletar)
        {
            ConcluirCarinho();
        }
    }

    /// <summary>
    /// Toca as partículas de conclusão na cabeça, avisa o backend
    /// quanto tempo o carinho levou, e encerra a sessão. concluido
    /// evita disparar isso mais de uma vez no mesmo frame ou em frames
    /// seguintes antes do GameObject desativar de verdade — e também
    /// impede que VerificarTimeout() dispare um timeout logo depois de
    /// uma conclusão bem-sucedida.
    /// </summary>
    private void ConcluirCarinho()
    {
        concluido = true;

        MostrarEfeitoConclusao();
        NotificarConcluido();

        Encerrar();
    }

    /// <summary>
    /// Dispara o texto flutuante de conclusão (ex: um coração que sobe
    /// e desaparece) na posição configurada — mesma ideia do
    /// MoodChangeIndicator, só que reaproveitada aqui em vez de um
    /// ParticleSystem, que era pesado demais pra esse feedback simples.
    /// </summary>
    private void MostrarEfeitoConclusao()
    {
        if (string.IsNullOrEmpty(textoEfeitoConclusao)) return;

        Vector3 posicaoEfeito = pontoEfeitoConclusao != null
            ? pontoEfeitoConclusao.position
            : (colisorCabeca != null ? colisorCabeca.bounds.center : transform.position);

        StartCoroutine(AnimarEfeitoConclusao(posicaoEfeito));
    }

    private IEnumerator AnimarEfeitoConclusao(Vector3 posicaoInicial)
    {
        GameObject obj = new GameObject("PetConclusaoTexto");
        TextMeshPro tmp = obj.AddComponent<TextMeshPro>();

        tmp.text = textoEfeitoConclusao;
        tmp.color = corEfeitoConclusao;
        tmp.fontSize = tamanhoFonteEfeitoConclusao;
        tmp.alignment = TextAlignmentOptions.Center;

        if (fonteEfeitoConclusao != null)
            tmp.font = fonteEfeitoConclusao;

        obj.transform.position = posicaoInicial;

        Vector3 posicaoFinal = posicaoInicial + Vector3.up * distanciaSubidaEfeitoConclusao;

        float elapsedTime = 0f;

        while (elapsedTime < duracaoEfeitoConclusao)
        {
            elapsedTime += Time.deltaTime;
            float progresso = Mathf.Clamp01(elapsedTime / duracaoEfeitoConclusao);

            obj.transform.position = Vector3.Lerp(posicaoInicial, posicaoFinal, progresso);

            if (Camera.main != null)
                obj.transform.rotation = Camera.main.transform.rotation;

            // Só começa a desaparecer na segunda metade da animação —
            // mesma curva usada em MoodChangeIndicator.AnimateText.
            if (progresso > 0.5f)
            {
                Color corAtual = tmp.color;
                corAtual.a = Mathf.Lerp(1f, 0f, (progresso - 0.5f) / 0.5f);
                tmp.color = corAtual;
            }

            yield return null;
        }

        Destroy(obj);
    }

    /// <summary>
    /// Avisa o backend Python (via VenusRequester, o mesmo entry point
    /// que PokeController usa) que o usuário completou o carinho,
    /// informando quanto tempo — em segundos inteiros, desde o
    /// Iniciar() que deu início a esta sessão — isso levou. A mensagem
    /// vai pra fila normal do /ask; a resposta de Venus chega depois,
    /// como sempre, via ResponseListener.
    /// </summary>
    private void NotificarConcluido()
    {
        float segundosDecorridos = Time.time - tempoInicioSessao;
        VenusRequester.Ask($"[System message: User petted your head in {segundosDecorridos:F0} seconds]");
    }

    /// <summary>
    /// Avisa o backend que o usuário não completou o carinho dentro de
    /// tempoLimiteSegundos.
    /// </summary>
    private void NotificarNaoConcluido()
    {
        VenusRequester.Ask("[System message: User didn't pet your head.]");
    }

    /// <summary>
    /// A fonte de som fica tocando continuamente (em loop) durante todo
    /// o arrasto — nunca é pausada/retomada, o que causava cliques e um
    /// pequeno atraso ao retomar. Em vez disso, o volume é interpolado
    /// suavemente em direção a volumeMaximoSomCarinho (quando a mão está
    /// se movendo) ou 0 (quando está parada), então a audibilidade muda
    /// de forma contínua, sem cortes abruptos na forma de onda.
    /// </summary>
    private void AtualizarSomCarinho(bool maoEstaMovendo)
    {
        if (fonteSomCarinho == null) return;

        volumeSomDesejado = maoEstaMovendo ? volumeMaximoSomCarinho : 0f;
        volumeSomAtual = Mathf.MoveTowards(volumeSomAtual, volumeSomDesejado, velocidadeFadeSomCarinho * Time.deltaTime);
        fonteSomCarinho.volume = volumeSomAtual;
    }

    private void AplicarImpulsoNaCabeca(Vector3 movimentoMundoNoFrame)
    {
        if (springCabeca == null || ossoCabeca == null) return;
        if (movimentoMundoNoFrame.sqrMagnitude < 0.0000001f) return;

        Vector3 direcaoMundo = movimentoMundoNoFrame.normalized;
        Vector3 eixoMundo = Vector3.Cross(direcaoMundo, Vector3.up);
        Vector3 eixoLocal = ossoCabeca.InverseTransformDirection(eixoMundo);

        float forca = Mathf.Min(movimentoMundoNoFrame.magnitude * sensibilidadeImpulso, impulsoMaximo);

        springCabeca.ApplyImpulse(eixoLocal, forca);

        // Além do impulso lateral vindo do movimento da mão, aplica um
        // pequeno impulso constante de inclinação pra frente — só nos
        // frames em que a mão está de fato se movendo (é por isso que
        // esse bloco vive dentro do "early return" de movimento acima):
        // segurar o botão parado no meio do arrasto não deve inclinar
        // a cabeça, só o próprio movimento.
        if (forcaInclinacaoFrente > 0f)
        {
            Vector3 eixoFrenteLocal = eixoInclinacaoFrenteLocal.sqrMagnitude > 0.0001f
                ? eixoInclinacaoFrenteLocal.normalized
                : Vector3.right;

            springCabeca.ApplyImpulse(eixoFrenteLocal, forcaInclinacaoFrente * Time.deltaTime);
        }
    }

    /// <summary>
    /// Inclina (roll) a mão em torno do eixo de visão da câmera — o
    /// mesmo eixo usado pra girar o arco — conforme anguloAtual se
    /// aproxima de anguloMaximoArco pra qualquer lado. Em
    /// anguloAtual == 0 a mão fica na rotação de repouso capturada em
    /// Iniciar(); no limite do arco ela chega a inclinacaoMaximaMao
    /// graus. curvaInclinacaoMao controla o formato da curva (1 =
    /// linear, >1 = quase reta até perto do fim, então inclina rápido).
    /// </summary>
    private void AtualizarInclinacaoMao()
    {
        if (cameraPrincipal == null || anguloMaximoArco <= 0.0001f || inclinacaoMaximaMao <= 0f) return;

        float proporcao = Mathf.Clamp(anguloAtual / anguloMaximoArco, -1f, 1f);
        float inclinacao = Mathf.Sign(proporcao) * Mathf.Pow(Mathf.Abs(proporcao), curvaInclinacaoMao) * inclinacaoMaximaMao;

        Quaternion rotacaoInclinacao = Quaternion.AngleAxis(inclinacao, cameraPrincipal.transform.forward);
        transform.rotation = rotacaoInclinacao * rotacaoBaseMao;
    }

    /// <summary>
    /// Interpola pesoOlhoAtual em direção a pesoOlhoDesejado (0 = olhos
    /// abertos, 1 = fechados) e escreve na expression do VRM
    /// (ExpressionKey.Blink) a cada frame em que a mão está ativa — não
    /// só enquanto arrastando é true — pra que a abertura dos olhos após
    /// soltar o mouse também seja suave, e não um corte seco.
    /// </summary>
    private void AtualizarFechamentoOlhos()
    {
        if (vrm10Instance == null) return;

        pesoOlhoAtual = Mathf.MoveTowards(pesoOlhoAtual, pesoOlhoDesejado, velocidadeFechamentoOlhos * Time.deltaTime);
        vrm10Instance.Runtime.Expression.SetWeight(ExpressionKey.Blink, pesoOlhoAtual);
    }
}