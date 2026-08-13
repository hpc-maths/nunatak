/* Network probe: a pingpong between rank 0 and the last rank.
 *
 * Latency is the best 8-byte round trip; bandwidth repetitions are
 * reported one line each and the driver keeps the maximum - like the
 * calibration kernel, the goal is an upper bound, so the best
 * repetition is the measurement and the others witness dispersion.
 * Every line is self-reported so a recorded run replays identically:
 *
 *   probe pingpong
 *   ranks <world size>
 *   latency_us <best 8-byte round trip, microseconds>
 *   bytes <message size>
 *   rep <index> <bytes per second>
 *
 * Usage: probe [repetitions] [message_bytes]
 * Ranks between 0 and the last only meet the barriers: the probe
 * measures one link, not a collective.
 */
#include <mpi.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char **argv) {
  MPI_Init(&argc, &argv);
  int rank, size;
  MPI_Comm_rank(MPI_COMM_WORLD, &rank);
  MPI_Comm_size(MPI_COMM_WORLD, &size);
  int repetitions = argc > 1 ? atoi(argv[1]) : 5;
  long bytes = argc > 2 ? atol(argv[2]) : (4L << 20);
  if (size < 2 || repetitions < 1 || bytes < 8) {
    if (rank == 0)
      fprintf(stderr, "probe: needs 2 ranks, positive repetitions, 8 bytes or more\n");
    MPI_Finalize();
    return 2;
  }
  int peer = size - 1;
  char *buffer = malloc((size_t)bytes);
  memset(buffer, 1, (size_t)bytes);

  double latency = -1.0;
  const int latency_trips = 1000;
  for (int rep = 0; rep < repetitions; rep++) {
    MPI_Barrier(MPI_COMM_WORLD);
    double start = MPI_Wtime();
    for (int trip = 0; trip < latency_trips; trip++) {
      if (rank == 0) {
        MPI_Send(buffer, 8, MPI_BYTE, peer, 0, MPI_COMM_WORLD);
        MPI_Recv(buffer, 8, MPI_BYTE, peer, 0, MPI_COMM_WORLD, MPI_STATUS_IGNORE);
      } else if (rank == peer) {
        MPI_Recv(buffer, 8, MPI_BYTE, 0, 0, MPI_COMM_WORLD, MPI_STATUS_IGNORE);
        MPI_Send(buffer, 8, MPI_BYTE, 0, 0, MPI_COMM_WORLD);
      }
    }
    double trip_time = (MPI_Wtime() - start) / (2.0 * latency_trips);
    if (rank == 0 && (latency < 0 || trip_time < latency))
      latency = trip_time;
  }

  if (rank == 0) {
    printf("probe pingpong\n");
    printf("ranks %d\n", size);
    printf("latency_us %.3f\n", latency * 1e6);
    printf("bytes %ld\n", bytes);
  }

  const int trips = 10;
  for (int rep = 0; rep < repetitions; rep++) {
    MPI_Barrier(MPI_COMM_WORLD);
    double start = MPI_Wtime();
    for (int trip = 0; trip < trips; trip++) {
      if (rank == 0) {
        MPI_Send(buffer, (int)bytes, MPI_BYTE, peer, 0, MPI_COMM_WORLD);
        MPI_Recv(buffer, (int)bytes, MPI_BYTE, peer, 0, MPI_COMM_WORLD, MPI_STATUS_IGNORE);
      } else if (rank == peer) {
        MPI_Recv(buffer, (int)bytes, MPI_BYTE, 0, 0, MPI_COMM_WORLD, MPI_STATUS_IGNORE);
        MPI_Send(buffer, (int)bytes, MPI_BYTE, 0, 0, MPI_COMM_WORLD);
      }
    }
    double elapsed = MPI_Wtime() - start;
    if (rank == 0)
      printf("rep %d %.6e\n", rep, (2.0 * trips * (double)bytes) / elapsed);
  }
  free(buffer);
  MPI_Finalize();
  return 0;
}
