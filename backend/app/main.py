"""API de Ballers.gg. Cada ruta recibe datos y llama a participantes.py."""
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from bd.conexion import engine, get_session
from . import participantes, sesiones, torneos, resultados, estadisticas
from .datos import ResultCreate, TournamentCreate, RegisterData, LoginData, ParticipantPage, ParticipantResponse, StateUpdate, StatusFilter, participant_to_dict

app = FastAPI(title='Ballers.gg · API de torneos', version='0.5.0', dependencies=[Depends(sesiones.require_access)],
              description='Participantes, torneos individuales y por parejas, ligas, resultados, estadísticas e historial en MariaDB.')


@app.exception_handler(SQLAlchemyError)
async def database_error(request: Request, error: SQLAlchemyError):
    # No mostrar detalles internos de la conexión ni credenciales.
    return JSONResponse(status_code=503, content={
        'detail': 'No se pudo acceder a MariaDB. Revisa la conexión y la preparación de tablas.',
    })


@app.get('/api/health', tags=['Sistema'])
def health():
    with engine.connect() as connection:
        connection.execute(text('SELECT 1'))
    return {'status': 'ok', 'database': 'MariaDB'}


def read_logo(logo):
    if logo is None:
        return None
    try:
        content = logo.file.read(participantes.MAX_LOGO_BYTES + 1)
        if len(content) > participantes.MAX_LOGO_BYTES:
            raise HTTPException(422, 'El logo no puede superar los 2 MB.')
        return content
    finally:
        logo.file.close()


@app.get('/api/participants', response_model=ParticipantPage)
def list_participants(
    q: str = Query('', max_length=100),
    status: StatusFilter = 'all',
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=48),
    session=Depends(get_session),
    identity=Depends(sesiones.require_access),
):
    return participantes.list_participants(session, q, status, page, page_size, identity)


@app.get('/api/participants/{participant_id}', response_model=ParticipantResponse)
def get_participant(participant_id: int, session=Depends(get_session), identity=Depends(sesiones.require_access)):
    participant = participantes.get_participant(session, participant_id, identity)
    return participant_to_dict(participant)


@app.post('/api/participants', response_model=ParticipantResponse, status_code=201)
def create_participant(
    nick: str = Form(..., max_length=100),
    is_active: bool = Form(True),
    logo: UploadFile | None = File(None),
    session=Depends(get_session),
    identity=Depends(sesiones.require_access),
):
    return participantes.create_participant(session, nick, is_active, read_logo(logo), identity)


@app.put('/api/participants/{participant_id}', response_model=ParticipantResponse)
def edit_participant(
    participant_id: int,
    nick: str = Form(..., max_length=100),
    is_active: bool = Form(...),
    version: int = Form(..., ge=1),
    remove_logo: bool = Form(False),
    logo: UploadFile | None = File(None),
    session=Depends(get_session),
    identity=Depends(sesiones.require_access),
):
    return participantes.edit_participant(
        session, participant_id, nick, is_active, version, read_logo(logo), remove_logo, identity,
    )


@app.patch('/api/participants/{participant_id}/state', response_model=ParticipantResponse)
def change_state(participant_id: int, payload: StateUpdate, session=Depends(get_session), identity=Depends(sesiones.require_access)):
    return participantes.change_state(session, participant_id, payload.is_active, payload.version, identity)


@app.get('/api/participants/{participant_id}/logo')
def get_logo(participant_id: int, session=Depends(get_session), identity=Depends(sesiones.require_access)):
    participant = participantes.get_participant(session, participant_id, identity)
    if participant.logo is None:
        raise HTTPException(404, 'Este participante no tiene logo.')
    return Response(
        participant.logo.content,
        media_type='image/png',
        headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'},
    )


@app.get('/api/auth/session', tags=['Acceso'])
def session_info(request: Request, response: Response, session=Depends(get_session)):
    sesiones.set_csrf(response, request)
    return sesiones.public_identity(sesiones.get_identity(request, session))


@app.post('/api/auth/register', tags=['Acceso'], status_code=201)
def register(payload: RegisterData, request: Request, response: Response, session=Depends(get_session)):
    return sesiones.register(payload, request, response, session)


@app.post('/api/auth/login', tags=['Acceso'])
def login(payload: LoginData, request: Request, response: Response, session=Depends(get_session)):
    return sesiones.login(payload, request, response, session)


@app.post('/api/auth/guest', tags=['Acceso'])
def guest(request: Request, response: Response, session=Depends(get_session)):
    return sesiones.start_guest(request, response, session)


@app.post('/api/auth/logout', tags=['Acceso'])
def logout(request: Request, response: Response, session=Depends(get_session)):
    sesiones.end_session(request, response, session)
    return {'authenticated': False, 'mode': None, 'username': None}


@app.middleware('http')
async def private_responses(request: Request, call_next):
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.get('/api/tournaments/eligible', tags=['Torneos'])
def tournament_candidates(session=Depends(get_session), identity=Depends(sesiones.require_access)):
    return torneos.eligible(session, identity)


@app.get('/api/tournaments', tags=['Torneos'])
def list_tournaments(page: int = Query(1,ge=1), page_size: int = Query(12,ge=1,le=48),
                     session=Depends(get_session), identity=Depends(sesiones.require_access)):
    return torneos.list_tournaments(session, identity, page, page_size)


@app.post('/api/tournaments', status_code=201, tags=['Torneos'])
def create_tournament(payload: TournamentCreate, session=Depends(get_session), identity=Depends(sesiones.require_access)):
    return torneos.create(session, payload, identity)


@app.get('/api/tournaments/{tournament_id}', tags=['Torneos'])
def get_tournament(tournament_id: int, session=Depends(get_session), identity=Depends(sesiones.require_access)):
    return torneos.detail(session, tournament_id, identity)


@app.post('/api/tournaments/{tournament_id}/matches/{match_id}/result', tags=['Resultados'])
def record_result(tournament_id: int, match_id: str, payload: ResultCreate,
                  session=Depends(get_session), identity=Depends(sesiones.require_access)):
    return resultados.record(session, tournament_id, match_id, payload, identity)


@app.delete('/api/tournaments/{tournament_id}', status_code=204, tags=['Torneos'])
def delete_tournament(tournament_id: int, version: int = Query(ge=1),
                      session=Depends(get_session), identity=Depends(sesiones.require_access)):
    torneos.remove(session,tournament_id,version,identity)
    return Response(status_code=204)


@app.get('/api/statistics', tags=['Estadísticas'])
def statistics(page: int=Query(1,ge=1),page_size: int=Query(12,ge=1,le=48),q: str=Query('',max_length=100),
               session=Depends(get_session),identity=Depends(sesiones.require_access)):
    return estadisticas.ranking(session,identity,page,page_size,q)


@app.get('/api/participants/{participant_id}/history', tags=['Estadísticas'])
def player_history(participant_id: int,page: int=Query(1,ge=1),page_size: int=Query(20,ge=1,le=48),
                   session=Depends(get_session),identity=Depends(sesiones.require_access)):
    return estadisticas.history(session,identity,participant_id,page,page_size)
