#!/usr/bin/python


import argparse
import os
from io import StringIO, BytesIO
import chess
import chess.pgn
import chess.svg
from reportlab.platypus import Table, Image, Frame, BaseDocTemplate, Paragraph, PageTemplate, SimpleDocTemplate
from reportlab.lib.units import cm
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus.flowables import KeepTogether, PageBreak

import re
import datetime

# TODO
# - immprove pdf-return/pdf-file-save
# - think about error handling
# - more comments

DISPLAY_JUST_WRONG_MOVES = True

MOVE_COMMENT_EXTRA_REGEX = re.compile(r"""\[[^\]]+([^\]]*)\]""")
CHESSCOM_CEFFECT_REGEX = re.compile(r"""\[%c_effect\s([a-h][1-8]);([a-zA-Z0-9;]+)\]""", re.VERBOSE)
CHESSCOM_CARROW_REGEX = re.compile(r"""\[%c_arrow\s([a-h][1-8])([a-h][1-8]);([#\.a-zA-Z0-9;]+)\]""", re.VERBOSE)

class GamePrinter:
    tile_padding = 0.1  # meaning 10% of width/height of tile == padded
    piece_images_path = 'piece_images/merida/72/'

    def __init__(self,
                 pgn,
                 output_path='',
                 filename='',
                 halfmoves_to_be_printed=list(),
                 dark_tile_color='#7C7671',
                 light_tile_color='#DCD7BC',
                 page_format=A4,
                 page_margin=1.27,  # in cm
                 font_name='Helvetica',
                 font_size=12,
                 space_before=6,
                 space_after=6,
                 col_gap=1,
                 # not yet implemented
                 page_layout='two_col',
                 page_numbering=None):
        self.read_games(pgn)
        self.pgn_filename = pgn
        self.output_path = output_path
        self.filename = filename if filename else '{}.pdf'.format(os.path.basename(pgn))
        self.halfmoves_to_be_printed = halfmoves_to_be_printed
        self.dark_tile_color = dark_tile_color
        self.light_tile_color = light_tile_color
        self.page_margin = page_margin
        self.font_name = font_name
        self.font_size = font_size
        self.space_before = space_before
        self.space_after = space_after
        self.col_gap = col_gap
        self.page_layout = page_layout
        self.page_numbering = page_numbering
        self.white_previous_clock = None
        self.black_previous_clock = None
        if page_format == 'letter':
            self.page_format = letter
        else:
            self.page_format = A4

    def init_reportlab(self, save_to_file=True):
        self.styles = getSampleStyleSheet()
        self.buff = BytesIO()
        self.doc = BaseDocTemplate(os.path.join(self.output_path, self.filename) if save_to_file else self.buff,
                                   pagesize=self.page_format,
                                   leftMargin=self.page_margin * cm,
                                   rightMargin=self.page_margin * cm,
                                   topMargin=self.page_margin * cm,
                                   bottomMargin=self.page_margin * cm,
                                   showBoundary=0,
                                   allowSplitting=1)
        # define styles for paragraphs
        self.styles.add(ParagraphStyle(
            'Header',
            fontSize=self.font_size,
            fontName=self.font_name,
            spaceBefore=self.space_before,
            spaceAfter=self.space_after,
            leading=self.font_size,
            alignment=TA_CENTER
        ))
        self.styles.add(ParagraphStyle(
            'Move_Text',
            fontSize=self.font_size,
            fontName=self.font_name,
            spaceBefore=self.space_before,
            spaceAfter=self.space_after,
            leading=self.font_size,
        ))
        # TODO: Add more Layouts
        if False:
            pass
        elif self.page_layout == 'two_col':
            frame_width = self.doc.width / 2 - self.col_gap / 2 * cm
            frame1 = Frame(self.doc.leftMargin, self.doc.bottomMargin, frame_width, self.doc.height, id='col1')
            frame2 = Frame(self.doc.leftMargin + frame_width + self.col_gap * cm, self.doc.bottomMargin, frame_width, self.doc.height, id='col2')
            self.doc.addPageTemplates([PageTemplate(id='twoCol', frames=[frame1, frame2])])
            # Set board dimensions relative to the two column layout
            self.board_length = 0.8 * frame_width / cm  # in cm
            self.tile_length = self.board_length / 8  # in cm

    def change_game(self, pgn):
        if type(pgn) == str and os.path.exists(pgn):
            with open(pgn) as f:
                self.games = [chess.pgn.read_game(f)]
        else:
            self.games = [chess.pgn.read_game(StringIO(pgn))]

    def read_games(self, pgn):
        if type(pgn) == str and os.path.exists(pgn):
            with open(pgn) as f:
                self.games = []
                game = chess.pgn.read_game(f)
                while game is not None:
                    self.games.append(game)
                    game = chess.pgn.read_game(f)
        else:
            self.games = [chess.pgn.read_game(StringIO(pgn))]

    def get_file_path(self):
        return os.path.join(self.output_path, self.doc_name)

    def board_from_FEN(self, fen):
        # Generate Data for Table from FEN-Code
        board_setup_fen = fen.split(' ')[0]
        rank_setup_fen = board_setup_fen.split('/')
        board_setup = []
        for rank in rank_setup_fen:
            rank_setup = []
            for tile in rank:
                if tile.isalpha():
                    piece = 'w{}'.format(tile.lower()) if tile.isupper() else 'b{}'.format(tile)
                    img_size = self.tile_length * (1 - self.tile_padding) * cm
                    img = Image('{}{}.png'.format(self.piece_images_path, piece), width=img_size, height=img_size)
                    rank_setup.append(img)
                elif tile.isdigit():
                    rank_setup += [None] * int(tile)
                else:
                    print('{} is not valid in {}'.format(tile, board_setup_fen))
            board_setup.append(rank_setup)
        # Arrange chess board as table
        table_style = [('ALIGN', (0, 0), (7, 7), 'CENTER'),
                       ('VALIGN', (0, 0), (7, 7), 'MIDDLE'),
                       ('BOX', (0, 0), (7, 7), 0.5, colors.grey)]
        # Color cells according to a chess board
        dark_tile_coords = [(i, j) for j in range(8) for i in range(8) if j % 2 == 1 and i % 2 == 0 or j % 2 == 0 and i % 2 == 1]
        light_tile_coords = [(i, j) for j in range(8) for i in range(8) if j % 2 == 0 and i % 2 == 0 or j % 2 == 1 and i % 2 == 1]
        table_style += [('BACKGROUND', coord, coord, self.dark_tile_color) for coord in dark_tile_coords]
        table_style += [('BACKGROUND', coord, coord, self.light_tile_color) for coord in light_tile_coords]
        return Table(board_setup, colWidths=[self.tile_length * cm] * 8, rowHeights=[self.tile_length * cm] * 8, style=table_style)

    def get_clean_move_comment(self, move, white_to_move):
        clk = move.clock()
        #print("\ncomment: {}, clk: {}".format(move.comment, clk))
        time_spent = 0
        if clk is not None:
            if white_to_move:
                if self.white_previous_clock != None:
                    time_spent = self.white_previous_clock - clk
                else:
                    time_spent = 0
                self.white_previous_clock = clk
                #print("  white: {}, time_spent: {}\n".format(self.white_previous_clock, time_spent))
            else:
                if self.black_previous_clock != None:
                    time_spent = self.black_previous_clock - clk
                else:
                    time_spent = 0
                self.black_previous_clock = clk
                #print("  black: {}, time_spent: {}\n".format(self.black_previous_clock, time_spent))

        str = '(spent: {}, left: {})'.format(datetime.timedelta(seconds=time_spent), datetime.timedelta(seconds=clk)) if clk is not None else ''
        move_comments = []

        _, move_comment, suggest_move_comment = self.explain_move(move)
        clean_comment = MOVE_COMMENT_EXTRA_REGEX.sub('', move.comment).strip()
        #print("  clean_comment: ({})\n\n".format(clean_comment))
        return ' '.join([str, move_comment, suggest_move_comment, clean_comment])

    def explain_move(self, move):
        match = CHESSCOM_CARROW_REGEX.search(move.comment)
        from_square = ''
        to_square = ''
        if match:
            from_square = match.group(1)
            to_square = match.group(2)
            arrow_move = '{} to {}'.format(from_square, to_square)
        else:
            arrow_move = ''
        # for match in CHESSCOM_CEFFECT_REGEX.finditer(move.comment):
        move_category, move_comment = self.get_move_category(move)
        if self.is_wrong_move(move_category) and arrow_move:
            piece = move.parent.board().piece_at(chess.parse_square(from_square))
            piece_name_to_move = chess.piece_name(piece.piece_type)
            piece_color_name = 'White' if (piece.color == chess.WHITE) else 'Black'
            suggest_move_comment = '{} should have played {} from {} to {} instead.'.format(piece_color_name, piece_name_to_move, from_square, to_square)
        else:
            suggest_move_comment = ''
        return move_category, move_comment, suggest_move_comment

    def is_wrong_move(self, move_category):
        return (move_category == 'MissedWin' or move_category == 'Mistake' or move_category == 'Inaccuracy' or move_category == 'Blunder')

    def get_move_category(self, move):
        # for match in CHESSCOM_CEFFECT_REGEX.finditer(move.comment):
        match = CHESSCOM_CEFFECT_REGEX.search(move.comment)
        move_category = ''
        if match:
            #for group in match.groups():
            #    print("  g: {}".format(group))
            #print("\n")
            move_category = match.group(2).split(';')[-1]
            # move_comment = '(move: {})'.format(move_category)
            move_comment = '<strong>{}</strong>! '.format(move_category)
        else:
            move_comment = ''
        return move_category, move_comment

    def print_move_and_variations(self, move, halfmove):
        # [move number (if white to move)] [move (san)] [comment]
        # examples: '1. e4', 'c5'
        move_number = int((halfmove + 2) / 2)
        white_to_move = halfmove % 2 == 0
        # Force print of move number for a black move
        move_comment = self.get_clean_move_comment(move, white_to_move)
        text = '<strong>{}{}</strong>{}'.format('{}. '.format(move_number) if white_to_move else '',
                                                move.san(),
                                                ' {}'.format(move_comment) if move_comment else '')
        # If game has variations at this point they will be printed including comments.
        # examples: 'c5 (1... e5 2. Nf3)', '2. Nf3 (2. d4 a more direct approach)'
        if len(move.parent.variations) > 1:
            for i in range(1, len(move.parent.variations)):
                text += ' (<i>'
                # This will only add the first move of the variation
                parent_variation_move_comment = self.get_clean_move_comment(move.parent.variations[i], white_to_move)
                text += '<strong>{}{}</strong>{}'.format('{}. '.format(move_number) if white_to_move else '{}... '.format(move_number),
                                                         move.parent.variations[i].san(),
                                                         ' {}'.format(parent_variation_move_comment) if parent_variation_move_comment else '')
                # For the following moves recursivly explore the variation tree
                # This will also include subvariations
                for j, var_move in enumerate(move.parent.variations[i].mainline()):
                    text += ' {}'.format(self.print_move_and_variations(var_move, halfmove + 1 + j))
                text += '</i>)'
        return text

    def create_and_return_document(self):
        self.init_reportlab(save_to_file=False)
        self.create_document()
        return self.buff


    def create_document(self):
        # elements will contain flowables for the build function
        elements = []
        game_num = 1
        # TODO: Stores everything in memory and then dumps all in one-shop, so
        # the memory requirement of this approach is  very high.
        # A better approach would be to incrementally build one game at a time
        # and keep generating pdf file for each of the game and reclaim
        # memory for objects each time.
        #
        # Question: Can we call self.doc.build(elements) multiple times?
        # Answer: Probably not!
        for game in self.games:
            #game.set_clock()
            #game.set_arrows()
            time_control = game.headers.get('TimeControl', None)
            self.white_previous_clock = float(time_control) if time_control is not None else None
            self.black_previous_clock = self.white_previous_clock
            # Paragraph for Heading and meta information
            paragraph = '<font size={}><strong>{}<i>{}</i><br/> vs.<br/>{}<i>{}</i></strong></font><br/>'.format(
                self.font_size + 2,
                game.headers.get('White'),
                ' [{}]'.format(game.headers.get('WhiteElo')) if game.headers.get('WhiteElo') else '',
                game.headers.get('Black'),
                ' [{}]'.format(game.headers.get('BlackElo')) if game.headers.get('BlackElo') else '')
            for key in game.headers.keys():
                if key != 'White' and key != 'Black' and key != 'WhiteElo' and key != 'BlackElo' and game.headers.get(key) != '?':
                    paragraph += '<br/>{}: {}'.format(key, game.headers.get(key))
            elements.append(Paragraph(paragraph, self.styles['Header']))
            # Generate paragraphs with move text and board diagramms
            paragraph = str()
            # Note that the variable move is of type chess.pgn.GameNode
            for i, move in enumerate(game.mainline()):
                move_category, move_comment = self.get_move_category(move)
                # do you want to display just the wrong
                if DISPLAY_JUST_WRONG_MOVES:
                    if not self.is_wrong_move(move_category):
                        continue

                # Save board for the move
                svg_filename = '{}-{}-{}.svg'.format(os.path.join(self.output_path, os.path.basename(self.pgn_filename)), game_num, i)
                open(svg_filename, 'w').write(chess.svg.board(move.board(), lastmove=move.move, arrows=move.arrows(), coordinates=True))

                #if move.comment and '<*>' in move.comment or any([i == halfmove for halfmove in self.halfmoves_to_be_printed]):
                if move.has_variation:
                    elements.append(Paragraph(paragraph, self.styles['Move_Text']))
                    elements.append(KeepTogether(self.board_from_FEN(move.board().fen())))
                    paragraph = str()
                # After print of a board diagramm if it's black's move print move number
                if any([i == halfmove for halfmove in self.halfmoves_to_be_printed]) and i % 2 == 1:
                    paragraph += '<strong>{}...</strong> {} '.format(int((i + 2) / 2), self.print_move_and_variations(move, i).replace('<*>', '').strip())
                else:
                    paragraph += self.print_move_and_variations(move, i).replace('<*>', '').strip() + ' '
            elements.append(Paragraph(paragraph, self.styles['Move_Text']))
            elements.append(PageBreak())
            game_num = game_num + 1
        self.doc.build(elements)


def run(args):
    # Parse moves to be printed with board
    halfmoves_to_be_printed = list()
    for token in args.printBoard.split(' '):
        # example: '3w' translates to halfmove number 4
        halfmove = int(token[:-1]) * 2
        halfmove -= 2 if token[-1] == 'w' else 1
        halfmoves_to_be_printed.append(halfmove)
    # Create a GamePrinter Object
    printer = GamePrinter(args.pgnPath,
                          output_path=args.outputPath,
                          filename=args.filename,
                          halfmoves_to_be_printed=halfmoves_to_be_printed,
                          page_margin=args.pageMargin,
                          font_name=args.fontName,
                          font_size=args.fontSize,
                          space_before=args.spaceBefore,
                          space_after=args.spaceAfter,
                          col_gap=args.columnGap)
    printer.init_reportlab()
    printer.create_document()


def main():
    parser = argparse.ArgumentParser(description="Pretty print for pgn")
    parser.add_argument('pgnPath',
                        help='specify the path to the pgn')
    parser.add_argument('-o',
                        '--outputPath',
                        type=str,
                        help='defines the output path',
                        default='')
    parser.add_argument('-n',
                        '--filename',
                        type=str,
                        help='Specify a filename. Default: "[White] - [Black].pdf"',
                        default='')
    parser.add_argument('-p',
                        '--printBoard',
                        help='Give a string of moves to be printed (e.g. "2w 3b 10w")',
                        default='1w')
    parser.add_argument('-fs',
                        '--fontSize',
                        type=int,
                        help='Set the font size',
                        default='10')
    parser.add_argument('-fn',
                        '--fontName',
                        help='set the font. Available: Helvetica, Times-Roman, Courier',
                        default='Helvetica')
    parser.add_argument('-sb',
                        '--spaceBefore',
                        type=int,
                        help='Set amount of space before every paragraph',
                        default=6)
    parser.add_argument('-sa',
                        '--spaceAfter',
                        type=int,
                        help='Set amount of space after every paragraph',
                        default=6)
    parser.add_argument('-pm',
                        '--pageMargin',
                        type=float,
                        help='Set margin (left, right, bottom, up) of page',
                        default=1.27)
    parser.add_argument('-cg',
                        '--columnGap',
                        type=float,
                        help='Set the width (in cm) between columns in two-column-layout',
                        default=1)
    parser.set_defaults(func=run)
    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
