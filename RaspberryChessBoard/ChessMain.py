# -*- coding: utf-8 -*-
"""
This is our maon driver. It will be responsible for handling user input
and displaying the current GameState object.
"""
import sys
import time

sys.path.append(".")

# from Chess import ChessEngine, SmartMoveFinder
import ChessEngine
import SmartMoveFinder

from ChessEngine import *
from SmartMoveFinder import *
import FieldConfig
import pygame as p
import os
from multiprocessing import Process, Queue

# our current path information:
current_path = os.path.dirname(__file__)  # Where your .py file is located
image_path = os.path.join(current_path, "images")  # The image folder path

# 400 is another good option and it depends on how good the
# images you have in terms of quality and resolution and 512 is a power of 2
BOARD_WIDTH = BOARD_HEIGHT = 512
MOVE_LOG_PANEL_WIDTH = 270
MOVE_LOG_PANEL_HEIGHT = BOARD_HEIGHT
# the chess board is 8x8 :)
DIMENSION = 8
SQ_SIZE = BOARD_HEIGHT // DIMENSION
# for animation later on
MAX_FPS = 15
IMAGES = {}


"""
As loading the images can be a costly process, we need to
initialize a global dictonary for images just once in the main.
Also, we put the loading images code in its own function, so we could
adapt that code easily later on or add another piece sets !!
"""


def loadImages():
    pieces = ["wp", "wN", "wB", "wR", "wQ", "wK", "bp", "bN", "bB", "bR", "bQ", "bK"]
    for piece in pieces:
        img = os.path.join(image_path, piece + ".png")
        IMAGES[piece] = p.transform.scale(p.image.load(img), (SQ_SIZE, SQ_SIZE))


""" The follwoing is the drive of our code which will handle user inputs and updating the graphics """


def main():
    p.init()
    p.display.set_caption("Chess")
    screen = p.display.set_mode((BOARD_WIDTH + MOVE_LOG_PANEL_WIDTH, BOARD_HEIGHT))
    clock = p.time.Clock()
    screen.fill(p.Color("white"))
    moveLogFont = p.font.SysFont("Arail", 20, False, False)
    gs = GameState()
    validMoves = gs.getValidMoves()
    # moveMade: a flag varible that keep tracks if a valid move has been made
    # so we can generate another new set of valid moves
    moveMade = False
    animate = False  # a flag to know when to use the animation function
    # we now load the images once before the (while true) loop
    loadImages()
    running = True
    sqSelected = ()  # simply to keep track of the last click for the user
    invalidSq = ()  # stores a square that was clicked but is invalid for moving (red)
    # playerClicks: is a list to keep track of player clicks
    # to act like a vector to move the piece from one square to another
    playerClicks = []
    gameOver = False
    # if a human is playing, then this will be true
    # and if an AI is playing it'll be false
    playerOne = True  # for white side
    playerTwo = True  # for black side
    AIThinking = False
    moveFinderProcess = None
    moveUndone = False
    while running:
        humanTurn = (gs.whiteToMove and playerOne) or (not gs.whiteToMove and playerTwo)
        for e in p.event.get():
            # handling the exit condition
            if e.type == p.QUIT:
                running = False
            # handle the user mouse input, simply the idea of click and go
            # we may be later add the functionality of drag and drop
            # note if we later added somthing like a dashboard to the
            # scree, we need to filter those locations as we just need
            # the locations on the actual board
            elif e.type == p.MOUSEBUTTONDOWN:
                if not gameOver:
                    location = p.mouse.get_pos()  # like its (x, y) location
                    x, y = location
                    # clicked in right panel (move log + UI)
                    if x >= BOARD_WIDTH:
                        # map to panel local coords
                        px = x - BOARD_WIDTH
                        py = y
                        # panel layout (must match drawRightPanel)
                        padding = 8
                        status_h = 40
                        half_w = (MOVE_LOG_PANEL_WIDTH - 3 * padding) // 2
                        btn_h = 36
                        btn_y = padding * 2 + status_h
                        # top status area
                        if padding <= py < padding + status_h:
                            # clicked status fields -> no action
                            pass
                        # buttons row
                        elif btn_y <= py < btn_y + btn_h:
                            # undo (left) or restart (right)
                            if padding <= px < padding + half_w:
                                # Undo
                                gs.undoMove()
                                validMoves = gs.getValidMoves()
                                sqSelected = ()
                                playerClicks = []
                                invalidSq = ()
                                moveMade = True
                                animate = False
                                if AIThinking and moveFinderProcess is not None:
                                    try:
                                        moveFinderProcess.terminate()
                                    except Exception:
                                        pass
                                    AIThinking = False
                                moveUndone = True
                            elif (2 * padding + half_w) <= px < (2 * padding + 2 * half_w):
                                # Restart
                                gs = GameState()
                                validMoves = gs.getValidMoves()
                                sqSelected = ()
                                playerClicks = []
                                invalidSq = ()
                                moveMade = False
                                animate = False
                                gameOver = False
                                if AIThinking and moveFinderProcess is not None:
                                    try:
                                        moveFinderProcess.terminate()
                                    except Exception:
                                        pass
                                    AIThinking = False
                                moveUndone = False
                            # else: click in panel margin -> ignore
                        else:
                            # click in move log area -> clear selections (existing behaviour)
                            sqSelected = ()
                            playerClicks = []
                            invalidSq = ()
                    else:
                        # board click
                        col = x // SQ_SIZE
                        row = y // SQ_SIZE
                        clicked = (row, col)
                        # If an invalid (rote) Auswahl aktiv ist, blockiere alle Klicks außer dem erneuten Klick
                        # auf genau dieses rote Feld. So muss die rote Markierung zuerst gelöscht werden.
                        if invalidSq != ():
                            if clicked == invalidSq:
                                # erneuter Klick auf das rote Feld löscht die Markierung
                                invalidSq = ()
                                sqSelected = ()
                                playerClicks = []
                            else:
                                # ignore other clicks solange invalidSq gesetzt ist
                                # (keine Auswahl oder Züge starten)
                                pass
                        else:
                            # kein rotes Feld aktiv — normale Verarbeitung
                            # click on previously marked invalid square clears it (handled above)
                            # clicking the currently selected square unselects it
                            if clicked == sqSelected:
                                sqSelected = ()
                                playerClicks = []
                                invalidSq = ()
                            else:
                                # If no piece currently selected, this click is a selection attempt.
                                if sqSelected == ():
                                    piece = gs.board[row][col]
                                    # Do NOT mark empty squares as invalid
                                    if piece == "--":
                                        # ignore empty selection (no feedback)
                                        pass
                                    else:
                                        # wrong color -> invalid selection
                                        if piece[0] != ("w" if gs.whiteToMove else "b"):
                                            invalidSq = clicked
                                            sqSelected = ()
                                            playerClicks = []
                                        else:
                                            # piece belongs to current player: check if it has legal moves
                                            hasMoves = any(
                                                m.startRow == row and m.startCol == col for m in validMoves
                                            )
                                            if not hasMoves:
                                                # invalid because of rules (e.g. pinned, no legal moves)
                                                invalidSq = clicked
                                                sqSelected = ()
                                                playerClicks = []
                                            else:
                                                # valid selection
                                                sqSelected = clicked
                                                playerClicks = [sqSelected]
                                else:
                                    # there is already a selected piece -> treat click as destination
                                    playerClicks.append(clicked)
                    if (
                        len(playerClicks) == 2 and humanTurn
                    ):  # after the second click, we need to move
                        move = Move(playerClicks[0], playerClicks[1], gs.board)
                        for i in range(len(validMoves)):
                            if move == validMoves[i]:
                                # print(move.getChessNotation()) # for debugging
                                gs.makeMove(validMoves[i])
                                moveMade = True
                                animate = True
                                sqSelected = ()  # reset for the next turn
                                playerClicks = []  # reset for the next turn
                                invalidSq = ()
                        if not moveMade:
                            # keep first selection only
                            if sqSelected != ():
                                playerClicks = [sqSelected]
                            else:
                                playerClicks = []
            # handling the key presses like ctrl+z, etc..
            elif e.type == p.KEYDOWN:
                if e.key == p.K_z:  # call undo when z is pressed
                    gs.undoMove()
                    sqSelected = ()
                    playerClicks = []
                    invalidSq = ()
                    moveMade = True
                    animate = False
                    gameOver = False
                    if AIThinking:
                        moveFinderProcess.terminate()
                        AIThinking = False
                    moveUndone = True
                if e.key == p.K_r:  # reset the board when r is pressed
                    gs = GameState()
                    validMoves = gs.getValidMoves()
                    sqSelected = ()
                    playerClicks = []
                    invalidSq = ()
                    moveMade = False
                    animate = False
                    gameOver = False
                    running = True
                    if AIThinking:
                        moveFinderProcess.terminate()  # threading error
                        AIThinking = False
                    moveUndone = False
        # handle the AI move finder
        if not gameOver and not humanTurn and not moveUndone:
            if not AIThinking:
                AIThinking = True
                print("thinking..")
                returnQueue = Queue()  # is used to pass data between threads
                moveFinderProcess = Process(
                    target=SmartMoveFinder.findBestMoveMinMax,
                    args=(
                        gs,
                        validMoves,
                        returnQueue,
                    ),
                )
                moveFinderProcess.start()
                if not moveFinderProcess.is_alive():
                    AIMove = returnQueue.get()
                    print("done thinking")
                    if AIMove is None:
                        AIMove = SmartMoveFinder.findRandomMoves(validMoves)
                    gs.makeMove(AIMove)
                    moveMade = True
                    animate = True
                    AIThinking = False
        # generate the new set of valid moves when
        # only a user makes a valid move before
        if moveMade:
            if animate:
                animateMove(gs.moveLog[-1], screen, gs.board, clock)
            validMoves = gs.getValidMoves()
            moveMade = False
            animate = False
            moveUndone = False
        drawGameState(screen, gs, validMoves, sqSelected, moveLogFont, invalidSq)
        # check if the game ends either by stalemate or by a checkmate
        if gs.checkmate or gs.stalemate:
            gameOver = True
            text = (
                "Stalemate"
                if gs.stalemate
                else "Black wins by checkmate"
                if gs.whiteToMove
                else "White wins by chekmate"
            )
            drawEndGameText(screen, text)
        clock.tick(MAX_FPS)
        p.display.flip()


""" responsible for the all the graphics needed for a current game state """


def drawGameState(screen, gs, validMoves, sqSelected, moveLogFont, invalidSq):
    drawBoard(screen)  # draw the squares on the board right :)
    highlightSquares(screen, gs, validMoves, sqSelected, invalidSq)
    drawPieces(screen, gs.board)  # just draw the pieces on the top of the board
    drawRightPanel(screen, gs, moveLogFont)


def drawBoard(screen):
    global colors
    colors = [p.Color("white"), p.Color("gray")]
    for r in range(DIMENSION):
        for c in range(DIMENSION):
            color = colors[(r + c) % 2]
            p.draw.rect(
                screen, color, p.Rect(c * SQ_SIZE, r * SQ_SIZE, SQ_SIZE, SQ_SIZE)
            )


""" highlight the square selected and valid moves for the piece selected """


def highlightSquares(screen, gs, validMoves, sqSelected, invalidSq):
    # highlight invalid selection (must be clicked again to clear) only if there is a piece
    if invalidSq != ():
        r, c = invalidSq
        if gs.board[r][c] != "--":
            s = p.Surface((SQ_SIZE, SQ_SIZE))
            s.set_alpha(150)
            rgb = FieldConfig.get_highlight_color("invalid")
            s.fill(p.Color(*rgb))
            screen.blit(s, (c * SQ_SIZE, r * SQ_SIZE))
    if sqSelected != ():
        r, c = sqSelected
        # make sure that each user can use highlighting ability for its own pieces
        if gs.board[r][c][0] == ("w" if gs.whiteToMove else "b"):
            # 1. highlight the selected square
            s = p.Surface((SQ_SIZE, SQ_SIZE))
            s.set_alpha(
                100
            )  # zero value is full transparentand 255 means no transperency
            rgb = FieldConfig.get_highlight_color("selected")
            s.fill(p.Color(*rgb))
            screen.blit(s, (c * SQ_SIZE, r * SQ_SIZE))
            # 2. highlight moves from that selected square
            # Use different color for capture targets (green) vs normal moves (yellow)
            for move in validMoves:
                if move.startRow == r and move.startCol == c:  # valid move for that piece
                    if move.isCapture:
                        rgb = FieldConfig.get_highlight_color("capture")
                    else:
                        rgb = FieldConfig.get_highlight_color("move")
                    s.fill(p.Color(*rgb))
                    screen.blit(s, (move.endCol * SQ_SIZE, move.endRow * SQ_SIZE))

def drawPieces(screen, board):
    for r in range(DIMENSION):
        for c in range(DIMENSION):
            piece = board[r][c]
            if piece != "--":  # it's really a piece and not an empty square
                screen.blit(
                    IMAGES[piece], p.Rect(c * SQ_SIZE, r * SQ_SIZE, SQ_SIZE, SQ_SIZE)
                )


""" the animation function """


def animateMove(move, screen, board, clock):
    global colors
    dR = move.endRow - move.startRow
    dC = move.endCol - move.startCol
    framesPerSquare = 10  # frames to move one square
    frameCount = (abs(dR) + abs(dC)) * framesPerSquare
    for frame in range(frameCount + 1):
        r, c = (
            move.startRow + dR * frame / frameCount,
            move.startCol + dC * frame / frameCount,
        )
        drawBoard(screen)
        drawPieces(screen, board)
        # erase the move from its ending square
        color = colors[(move.endRow + move.endCol) % 2]
        endSquare = p.Rect(
            move.endCol * SQ_SIZE, move.endRow * SQ_SIZE, SQ_SIZE, SQ_SIZE
        )
        p.draw.rect(screen, color, endSquare)
        # draw the captured piece back onto the top of the rect
        if move.pieceCaptured != "--":
            if move.isEnpassantMove:
                enpassantRow = (
                    (move.endRow + 1)
                    if move.pieceCaptured[0] == "b"
                    else (move.endRow - 1)
                )
                endSquare = p.Rect(
                    move.endCol * SQ_SIZE, enpassantRow * SQ_SIZE, SQ_SIZE, SQ_SIZE
                )
            screen.blit(IMAGES[move.pieceCaptured], endSquare)
        # draw the moving piece
        screen.blit(
            IMAGES[move.pieceMoved], p.Rect(c * SQ_SIZE, r * SQ_SIZE, SQ_SIZE, SQ_SIZE)
        )
        p.display.flip()
        clock.tick(120)


def drawEndGameText(screen, text):
    font = p.font.SysFont("Helvitca", 32, True, False)
    textObject = font.render(text, 0, p.Color("Gray"))
    textLocation = p.Rect(0, 0, BOARD_WIDTH, BOARD_HEIGHT).move(
        BOARD_WIDTH / 2 - textObject.get_width() / 2,
        BOARD_HEIGHT / 2 - textObject.get_height() / 2,
    )
    screen.blit(textObject, textLocation)
    textObject = font.render(text, 0, p.Color("Black"))
    screen.blit(textObject, textLocation.move(2, 2))


def drawRightPanel(screen, gs, font):
    # Draw background
    panel_rect = p.Rect(BOARD_WIDTH, 0, MOVE_LOG_PANEL_WIDTH, MOVE_LOG_PANEL_HEIGHT)
    p.draw.rect(screen, p.Color("black"), panel_rect)

    padding = 8
    status_h = 40
    half_w = (MOVE_LOG_PANEL_WIDTH - 3 * padding) // 2
    # Status rects
    rect_black = p.Rect(BOARD_WIDTH + padding, padding, half_w, status_h)
    rect_white = p.Rect(BOARD_WIDTH + 2 * padding + half_w, padding, half_w, status_h)

    # Draw status backgrounds
    p.draw.rect(screen, p.Color("darkgray"), rect_black)
    p.draw.rect(screen, p.Color("darkgray"), rect_white)
    # Highlight active player
    active_rgb = FieldConfig.get_highlight_color("capture")
    if not gs.whiteToMove:
        p.draw.rect(screen, p.Color(*active_rgb), rect_black)
    else:
        p.draw.rect(screen, p.Color(*active_rgb), rect_white)

    # Texts
    black_text = font.render("Schwarz ist am Zug", True, p.Color("black"))
    white_text = font.render("Weiss ist am Zug", True, p.Color("black"))
    screen.blit(black_text, rect_black.move((rect_black.width - black_text.get_width()) // 2,
                                           (rect_black.height - black_text.get_height()) // 2))
    screen.blit(white_text, rect_white.move((rect_white.width - white_text.get_width()) // 2,
                                           (rect_white.height - white_text.get_height()) // 2))

    # Buttons
    btn_h = 36
    btn_y = padding * 2 + status_h
    btn_undo = p.Rect(BOARD_WIDTH + padding, btn_y, half_w, btn_h)
    btn_restart = p.Rect(BOARD_WIDTH + 2 * padding + half_w, btn_y, half_w, btn_h)
    p.draw.rect(screen, p.Color("lightgray"), btn_undo)
    p.draw.rect(screen, p.Color("lightgray"), btn_restart)
    p.draw.rect(screen, p.Color("black"), btn_undo, 2)
    p.draw.rect(screen, p.Color("black"), btn_restart, 2)
    undo_text = font.render("Zurueck", True, p.Color("black"))
    restart_text = font.render("Neustart", True, p.Color("black"))
    screen.blit(undo_text, btn_undo.move((btn_undo.width - undo_text.get_width()) // 2,
                                        (btn_undo.height - undo_text.get_height()) // 2))
    screen.blit(restart_text, btn_restart.move((btn_restart.width - restart_text.get_width()) // 2,
                                               (btn_restart.height - restart_text.get_height()) // 2))

    # Move log under buttons
    moveLog = gs.moveLog
    moveTexts = []
    for i in range(0, len(moveLog), 2):
        moveString = str(i // 2 + 1) + ". " + str(moveLog[i]) + " "
        if i + 1 < len(moveLog):
            moveString += str(moveLog[i + 1])
        moveTexts.append(moveString)
    textY = btn_y + btn_h + padding
    lineSpacing = 5
    for t in moveTexts:
        textObject = font.render(t, True, p.Color("white"))
        screen.blit(textObject, (BOARD_WIDTH + padding, textY))
        textY += textObject.get_height() + lineSpacing


if __name__ == "__main__":
    main()
